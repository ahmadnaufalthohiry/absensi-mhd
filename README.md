# Absensi Guru MHD Mubarokulhuda (Flask + SQLite)

## Menjalankan
    pip install -r requirements.txt
    python app.py        # buka http://localhost:5000
Akun contoh: admin / admin123 dan ustadz1 / guru123 (ganti segera). Atur `SECRET_KEY` di produksi.
Kamera browser hanya jalan di `localhost` atau HTTPS.

## Peta belajar (urutan baca yang disarankan)
1. `SCHEMA` di app.py: jadwal = rencana, absensi = kenyataan (jam jadwal disalin ke absensi agar riwayat aman).
2. `masuk()` dan `pulang()`: aturan bisnis (jendela waktu, status terlambat, waktu dari server, foto wajib).
3. `data_rekap()`: rekap hanyalah query atas tabel absensi dengan rentang tanggal (mingguan/bulanan sama saja).
4. `templates/`: tampilan Jinja2; JS kamera ada di base.html.
Foto tersimpan di `data/foto` dan hanya bisa dibuka lewat `/foto/<nama>` oleh admin atau pemilik.
Tampilan: static/style.css (gaya) dan static/app.js (kamera, jam, interaksi).
