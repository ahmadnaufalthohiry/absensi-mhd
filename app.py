import os, base64, sqlite3, io
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import (Flask, g, render_template, request, redirect, session,
                   send_from_directory, abort, flash, send_file)
from werkzeug.security import generate_password_hash, check_password_hash
from openpyxl import Workbook
from math import radians, sin, cos, asin, sqrt

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("ABSENSI_DATA", os.path.join(BASE, "data"))
DB, FOTO = os.path.join(DATA, "absensi.db"), os.path.join(DATA, "foto")  # foto disimpan privat
WIB = timezone(timedelta(hours=7))
TOLERANSI = 10   # menit boleh telat
SEBELUM = 60     # menit sebelum jadwal absen masuk sudah boleh
MAX_AKURASI = 100  # meter; GPS yang lebih kasar dari ini ditolak
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ganti-ini-di-produksi")
now = lambda: datetime.now(WIB)

SCHEMA = """
create table if not exists lokasi(id integer primary key, nama text unique);
create table if not exists users(id integer primary key, nama text, username text unique, password text, role text);
create table if not exists jadwal(id integer primary key, user_id int, lokasi_id int, hari int, jam_masuk text, jam_pulang text);
create table if not exists absensi(id integer primary key, jadwal_id int, user_id int, lokasi_id int, tanggal text,
  jam_masuk text, jam_pulang text, waktu_masuk text, foto_masuk text, materi text,
  waktu_pulang text, foto_pulang text, target text, kendala text, status text, unique(jadwal_id, tanggal));
"""

def init_db():
    os.makedirs(FOTO, exist_ok=True)
    c = sqlite3.connect(DB); c.executescript(SCHEMA)
    if not c.execute("select 1 from users").fetchone():
        for n in ("MHD Pusat (Kamasan)", "MHD Lokal 2 (Sukarame)", "MHD Lokal 3 (Sindangsari)"):
            c.execute("insert into lokasi(nama) values(?)", (n,))
        c.execute("insert into users(nama,username,password,role) values('Admin','admin',?,'admin')", (generate_password_hash("admin123"),))
        c.execute("insert into users(nama,username,password,role) values('Ustadz Contoh','ustadz1',?,'guru')", (generate_password_hash("guru123"),))
        c.execute("insert into jadwal(user_id,lokasi_id,hari,jam_masuk,jam_pulang) values(2,1,-1,'13:00','15:00')")
        for tbl, kol in (("lokasi", "lat real"), ("lokasi", "lng real"), ("lokasi", "radius int default 100"),
                     ("absensi", "jarak_masuk real"), ("absensi", "jarak_pulang real")):
            if kol.split()[0] not in [r[1] for r in c.execute(f"pragma table_info({tbl})")]:
                c.execute(f"alter table {tbl} add column {kol}")
    c.commit(); c.close()

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def tutup(_):
    d = g.pop("db", None)
    if d: d.close()

def login_required(role=None):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if "uid" not in session: return redirect("/login")
            if role and session["role"] != role: abort(403)
            return f(*a, **k)
        return w
    return deco

def simpan_foto(data, prefix):
    try: raw = base64.b64decode((data or "").split(",", 1)[1])
    except Exception: abort(400)
    if raw[:3] != b"\xff\xd8\xff" or len(raw) > 3_000_000: abort(400)  # harus JPEG, maks 3MB
    nama = f"{prefix}_{now():%Y%m%d%H%M%S}.jpg"
    open(os.path.join(FOTO, nama), "wb").write(raw)
    return nama

@app.route("/")
def index():
    return redirect("/admin" if session.get("role") == "admin" else "/guru")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db().execute("select * from users where username=?", (request.form["username"],)).fetchone()
        if u and check_password_hash(u["password"], request.form["password"]):
            session.update(uid=u["id"], nama=u["nama"], role=u["role"])
            return redirect("/")
        flash("Username atau password salah.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear(); return redirect("/login")

# ---------- GURU ----------
@app.route("/guru")
@login_required("guru")
def guru():
    t = now()
    rows = db().execute("""select j.*, l.nama lokasi, a.id aid, a.waktu_masuk, a.waktu_pulang, a.status, a.materi
        from jadwal j join lokasi l on l.id=j.lokasi_id
        left join absensi a on a.jadwal_id=j.id and a.tanggal=?
        where j.user_id=? and (j.hari=-1 or j.hari=?) order by j.jam_masuk""",
        (t.date().isoformat(), session["uid"], t.weekday())).fetchall()
    riwayat = db().execute("""select a.*, l.nama lokasi from absensi a join lokasi l on l.id=a.lokasi_id
        where a.user_id=? order by a.tanggal desc, a.jam_masuk desc limit 15""", (session["uid"],)).fetchall()
    return render_template("guru.html", rows=rows, riwayat=riwayat, tgl=f"{HARI[t.weekday()]}, {t:%d-%m-%Y}")

def jarak_m(lat1, lng1, lat2, lng2):  # rumus Haversine, hasil dalam meter
    p1, p2 = radians(lat1), radians(lat2)
    h = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lng2 - lng1) / 2) ** 2
    return 2 * 6371000 * asin(sqrt(h))

def cek_lokasi(lokasi_id):
    """Jarak (meter) jika boleh absen; None jika ditolak (alasan sudah di-flash)."""
    l = db().execute("select * from lokasi where id=?", (lokasi_id,)).fetchone()
    try: lat, lng, acc = (float(request.form[k]) for k in ("lat", "lng", "acc"))
    except (KeyError, ValueError):
        flash("Lokasi GPS tidak terbaca. Izinkan akses lokasi lalu coba lagi."); return None
    if l["lat"] is None:
        flash("Koordinat lokasi ini belum diatur oleh admin."); return None
    if acc > MAX_AKURASI:
        flash(f"Sinyal GPS lemah (akurasi ±{acc:.0f} m). Coba di tempat terbuka."); return None
    d, r = jarak_m(lat, lng, l["lat"], l["lng"]), l["radius"] or 100
    if d > r:
        flash(f"Anda berada {d:.0f} m dari {l['nama']}. Absen hanya bisa maksimal {r} m dari lokasi."); return None
    return d

@app.post("/absen/masuk/<int:jid>")
@login_required("guru")
def masuk(jid):
    j = db().execute("select * from jadwal where id=? and user_id=?", (jid, session["uid"])).fetchone() or abort(404)
    t = now(); tgl = t.date().isoformat()
    jam = datetime.fromisoformat(f"{tgl}T{j['jam_masuk']}").replace(tzinfo=WIB)
    if j["hari"] not in (-1, t.weekday()): abort(400)
    if t < jam - timedelta(minutes=SEBELUM):
        flash("Belum waktunya absen masuk."); return redirect("/guru")
    materi = request.form.get("materi", "").strip()
    if not materi:
        flash("Materi yang akan diajarkan wajib diisi."); return redirect("/guru")
    d = cek_lokasi(j["lokasi_id"])
    if d is None: return redirect("/guru")
    foto = simpan_foto(request.form.get("foto"), f"in{jid}")
    status = "Terlambat" if t > jam + timedelta(minutes=TOLERANSI) else "Tepat waktu"
    try:
        db().execute("""insert into absensi(jadwal_id,user_id,lokasi_id,tanggal,jam_masuk,jam_pulang,waktu_masuk,foto_masuk,materi,status,jarak_masuk)
            values(?,?,?,?,?,?,?,?,?,?,?)""", (jid, session["uid"], j["lokasi_id"], tgl, j["jam_masuk"], j["jam_pulang"],
            f"{t:%H:%M:%S}", foto, materi, status, round(d)))
        db().commit(); flash(f"Absen masuk tercatat ({status}).")
    except sqlite3.IntegrityError:
        flash("Anda sudah absen masuk untuk jadwal ini.")
    return redirect("/guru")

@app.post("/absen/pulang/<int:aid>")
@login_required("guru")
def pulang(aid):
    a = db().execute("select * from absensi where id=? and user_id=? and waktu_pulang is null",
                     (aid, session["uid"])).fetchone() or abort(404)
    target, kendala = request.form.get("target"), request.form.get("kendala", "").strip()
    if target not in ("Tercapai", "Sebagian", "Tidak tercapai"): abort(400)
    if target != "Tercapai" and not kendala:
        flash("Jelaskan kendala yang dihadapi."); return redirect("/guru")
    d = cek_lokasi(a["lokasi_id"])
    if d is None: return redirect("/guru")
    foto = simpan_foto(request.form.get("foto"), f"out{aid}")
    db().execute("update absensi set waktu_pulang=?, foto_pulang=?, target=?, kendala=?, jarak_pulang=? where id=?",
                 (f"{now():%H:%M:%S}", foto, target, kendala, round(d), aid))
    db().commit(); flash("Absen pulang tercatat."); return redirect("/guru")

@app.route("/foto/<nama>")
@login_required()
def foto(nama):
    if session["role"] != "admin" and not db().execute(
        "select 1 from absensi where (foto_masuk=? or foto_pulang=?) and user_id=?", (nama, nama, session["uid"])).fetchone():
        abort(403)
    return send_from_directory(FOTO, nama)

# ---------- ADMIN ----------
def label_hari(hs):
    if hs[0] == -1: return "Setiap hari"
    n = [h[:3] for h in HARI]; out = []; i = 0
    while i < len(hs):
        j = i
        while j + 1 < len(hs) and hs[j + 1] == hs[j] + 1: j += 1
        out.append(f"{n[hs[i]]}–{n[hs[j]]}" if j - i >= 2 else ", ".join(n[h] for h in hs[i:j + 1]))
        i = j + 1
    return ", ".join(out)

@app.route("/admin")
@login_required("admin")
def admin():
    d = db()
    rows = d.execute("""select j.*, u.nama guru, l.nama lokasi from jadwal j join users u on u.id=j.user_id
        join lokasi l on l.id=j.lokasi_id order by u.nama, j.user_id, j.hari""").fetchall()
    per_guru = {}  # user_id -> {guru, blok}; blok digabung jika lokasi dan jam sama
    for j in rows:
        g = per_guru.setdefault(j["user_id"], {"guru": j["guru"], "blok": {}})
        b = g["blok"].setdefault((j["lokasi"], j["jam_masuk"], j["jam_pulang"]), {"hari": [], "ids": []})
        b["hari"].append(j["hari"]); b["ids"].append(str(j["id"]))
    jadwal = [{"guru": g["guru"], "blok": [
        {"lokasi": k[0], "jam": f"{k[1]}–{k[2]}", "hari": label_hari(v["hari"]), "ids": ",".join(v["ids"])}
        for k, v in sorted(g["blok"].items(), key=lambda kv: min(kv[1]["hari"]))]} for g in per_guru.values()]
    return render_template("admin.html", hari=HARI, jadwal=jadwal,
        lokasi=d.execute("select * from lokasi").fetchall(),
        gurus=d.execute("select * from users where role='guru'").fetchall())

@app.post("/admin/guru")
@login_required("admin")
def tambah_guru():
    try:
        db().execute("insert into users(nama,username,password,role) values(?,?,?,'guru')",
            (request.form["nama"], request.form["username"], generate_password_hash(request.form["password"])))
        db().commit()
    except sqlite3.IntegrityError: flash("Username sudah dipakai.")
    return redirect("/admin")

@app.post("/admin/jadwal")
@login_required("admin")
def tambah_jadwal():
    f = request.form
    hari_list = [h for h in f.getlist("hari") if h in "0123456"]
    if not hari_list:
        flash("Pilih minimal satu hari."); return redirect("/admin")
    for h in hari_list:  # satu baris per hari
        db().execute("insert into jadwal(user_id,lokasi_id,hari,jam_masuk,jam_pulang) values(?,?,?,?,?)",
            (f["user_id"], f["lokasi_id"], int(h), f["jam_masuk"], f["jam_pulang"]))
    db().commit()
    flash(f"{len(hari_list)} jadwal ditambahkan.")
    return redirect("/admin")

@app.post("/admin/jadwal/hapus")
@login_required("admin")
def hapus_jadwal():
    ids = [i for i in request.form.get("ids", "").split(",") if i.isdigit()]
    db().executemany("delete from jadwal where id=?", [(i,) for i in ids])
    db().commit(); return redirect("/admin")

@app.post("/admin/lokasi/<int:lid>")
@login_required("admin")
def set_lokasi(lid):
    f = request.form
    try: lat, lng, r = float(f["lat"]), float(f["lng"]), int(f["radius"])
    except (KeyError, ValueError): flash("Koordinat atau radius tidak valid."); return redirect("/admin")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180 and r > 0): flash("Nilai di luar batas."); return redirect("/admin")
    db().execute("update lokasi set lat=?, lng=?, radius=? where id=?", (lat, lng, r, lid)); db().commit()
    flash("Lokasi disimpan."); return redirect("/admin")

# ---------- REKAP (rentang tanggal bebas: mingguan, bulanan, dst) ----------
def data_rekap():
    t = now().date()
    dari = request.args.get("dari") or t.replace(day=1).isoformat()
    sampai = request.args.get("sampai") or t.isoformat()
    lok = request.args.get("lokasi", "")
    q = """select a.*, u.nama guru, l.nama lokasi from absensi a join users u on u.id=a.user_id
           join lokasi l on l.id=a.lokasi_id where a.tanggal between ? and ?"""
    p = [dari, sampai]
    if lok: q += " and a.lokasi_id=?"; p.append(lok)
    return dari, sampai, lok, db().execute(q + " order by a.tanggal, u.nama", p).fetchall()

@app.route("/rekap")
@login_required("admin")
def rekap():
    dari, sampai, lok, rows = data_rekap()
    ringkas = {}
    for r in rows:
        s = ringkas.setdefault(r["guru"], {"sesi": 0, "telat": 0, "lengkap": 0})
        s["sesi"] += 1; s["telat"] += r["status"] == "Terlambat"; s["lengkap"] += bool(r["waktu_pulang"])
    return render_template("rekap.html", rows=rows, ringkas=ringkas, dari=dari, sampai=sampai, lok=lok,
                           lokasi=db().execute("select * from lokasi").fetchall(), qs=request.query_string.decode())

@app.route("/rekap.xlsx")
@login_required("admin")
def rekap_xlsx():
    _, _, _, rows = data_rekap()
    wb = Workbook(); ws = wb.active; ws.title = "Rekap"
    ws.append(["Tanggal", "Guru", "Lokasi", "Jadwal", "Masuk", "Pulang", "Status", "Materi", "Target", "Kendala"])
    for r in rows:
        ws.append([r["tanggal"], r["guru"], r["lokasi"], f"{r['jam_masuk']}-{r['jam_pulang']}", r["waktu_masuk"],
                   r["waktu_pulang"], r["status"], r["materi"], r["target"], r["kendala"]])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="rekap-absensi.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

init_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
