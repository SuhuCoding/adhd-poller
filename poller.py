# -*- coding: utf-8 -*-
"""
PENGINTAI PERINTAH — dipasang di repo baru 'adhd-poller' (Public).

Tugasnya: tiap 5 menit melihat apakah kamu menekan tombol atau mengetik
perintah di Telegram. Kalau ya, dia menyuruh repo bot yang tepat bekerja.

Tidak ada rahasia di dalam file ini. Semua token disimpan di
Settings > Secrets, dan Secrets tidak terlihat oleh siapa pun,
termasuk orang yang membuka repo Public ini.

File ini hanya memakai pustaka bawaan Python, jadi tidak perlu install apa pun.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

API_TG = "https://api.telegram.org/bot{token}/{metode}"

# kode persona -> nama secret yang berisi alamat repo
TUJUAN = {
    "umum": "REPO_UMUM",
    "anak": "REPO_ANAK",
    "orangtua": "REPO_ORANGTUA",
    "video": "REPO_VIDEO",
}

LABEL = {
    "umum": "📝 Artikel ADHD Umum",
    "anak": "🧒 Sudut Pandang Anak",
    "orangtua": "👨‍👩‍👦 Sudut Pandang Orang Tua",
    "video": "🎬 Script Video ADHD",
}

PERINTAH = {
    "/umum": ["umum"],
    "/anak": ["anak"],
    "/orangtua": ["orangtua"],
    "/video": ["video"],
    "/semua": ["umum", "anak", "orangtua", "video"],
}

BANTUAN = (
    "<b>Perintah yang tersedia</b>\n\n"
    "/id — tampilkan CHAT ID dan TOPIC ID tempat ini\n"
    "/stok — lihat daftar topik di gudang\n"
    "/umum — artikel ADHD umum\n"
    "/anak — narasi sudut pandang anak\n"
    "/orangtua — narasi sudut pandang orang tua\n"
    "/video — script video\n"
    "/semua — keempatnya sekaligus\n\n"
    "Tambahkan nomor topik untuk memilih bahan tertentu:\n"
    "<code>/anak 3</code> → narasi anak dari topik T3\n"
    "<code>/semua 2</code> → keempat script dari topik T2\n\n"
    "Tanpa nomor, bot memakai topik terbaik yang belum pernah dipakai.\n"
    "Hasil masuk 1–8 menit setelah perintah."
)


def minta(url, data=None, headers=None, metode=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=metode,
                                 headers=headers or {})
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            isi = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(isi) if isi.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {"raw": e.read().decode("utf-8", "replace")[:300]}
    except Exception as e:
        return 0, {"raw": str(e)[:300]}


def tg(token, metode, data=None):
    return minta(API_TG.format(token=token, metode=metode), data)


def kirim_pesan(token, chat_id, teks, thread=None):
    data = {"chat_id": chat_id, "text": teks, "parse_mode": "HTML",
            "disable_web_page_preview": True}
    if thread:
        data["message_thread_id"] = thread
    tg(token, "sendMessage", data)


def baca_gudang(pat, repo):
    """Ambil shared/topics.json dari repo materi_bot."""
    status, hasil = minta(
        f"https://api.github.com/repos/{repo}/contents/shared/topics.json",
        headers={"Authorization": f"Bearer {pat}",
                 "Accept": "application/vnd.github.raw",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "adhd-poller"})
    if status != 200:
        return None, status
    return hasil, 200


def teks_stok(paket):
    topics = paket.get("topics") or []
    if not topics:
        return ("🗂 <b>Gudang masih kosong.</b>\n\nBelum ada berita ADHD anak "
                "yang lolos saringan. Begitu ada, otomatis masuk ke gudang.")
    baris = [f"🗂 <b>GUDANG BAHAN</b> — {len(topics)} topik\n"
             f"Diperbarui: {paket.get('tanggal_wib', '-')}\n"]
    for t in topics:
        tag = " · ".join((t.get("gejala") or [])[:2]) or "Umum ADHD"
        baris.append(f"\n<b>{t.get('id', '?').upper()}</b> · "
                     f"{t.get('judul', '')[:95]}\n"
                     f"   🏷 {tag} · skor {t.get('skor', '-')}\n")
    baris.append("\nContoh pakai: <code>/anak 3</code>")
    return "".join(baris)


def potong(teks, batas=3800):
    hasil, buf = [], ""
    for b in teks.split("\n"):
        if len(buf) + len(b) + 1 > batas:
            hasil.append(buf)
            buf = ""
        buf += b + "\n"
    if buf.strip():
        hasil.append(buf)
    return hasil


def suruh_kerja(pat, repo, kode, topic_id):
    payload = {"persona": kode}
    if topic_id:
        payload["topic_id"] = topic_id
    status, hasil = minta(
        f"https://api.github.com/repos/{repo}/dispatches",
        {"event_type": "buat_script", "client_payload": payload},
        headers={"Authorization": f"Bearer {pat}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "adhd-poller"})
    # 204 = berhasil (GitHub tidak mengirim isi balasan)
    return status == 204, status, hasil


def urai_nomor(sisa):
    """'3' atau 't3' -> 't3'. Kalau bukan angka, kembalikan None."""
    m = re.match(r"^t?(\d{1,2})$", (sisa or "").strip())
    return f"t{int(m.group(1))}" if m else None


def main():
    token = os.environ.get("MATERI_BOT_TOKEN", "").strip()
    pat = os.environ.get("GH_PAT", "").strip()
    source = os.environ.get("SOURCE_REPO", "").strip()
    if not token or not pat:
        print("!! MATERI_BOT_TOKEN atau GH_PAT belum diisi di Secrets.")
        return 1

    status, hasil = tg(token, "getUpdates",
                       {"timeout": 0,
                        "allowed_updates": ["callback_query", "message"]})
    if status != 200 or not hasil.get("ok"):
        print(f"!! Gagal baca Telegram (status {status}): {str(hasil)[:250]}")
        return 1

    updates = hasil.get("result", [])
    print(f"{len(updates)} pesan/tombol menunggu diproses.")
    if not updates:
        return 0

    terakhir = 0
    tugas = []                  # (kode_persona, topic_id, chat_id)

    for u in updates:
        terakhir = max(terakhir, u.get("update_id", 0))

        cb = u.get("callback_query")
        if cb:
            data = cb.get("data") or ""
            pesan_cb = cb.get("message") or {}
            chat_id = (pesan_cb.get("chat") or {}).get("id")
            thread = pesan_cb.get("message_thread_id")
            tg(token, "answerCallbackQuery",
               {"callback_query_id": cb.get("id"), "text": "Diproses…"})
            if data.startswith("gen:"):
                pilih = data.split(":", 1)[1]
                kodenya = (list(TUJUAN) if pilih == "semua"
                           else ([pilih] if pilih in TUJUAN else []))
                for k in kodenya:
                    tugas.append((k, None, chat_id, thread))
            continue

        msg = u.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        thread = msg.get("message_thread_id")
        teks = (msg.get("text") or "").strip()
        if not teks.startswith("/"):
            continue

        bagian = teks.split()
        perintah = bagian[0].lower().split("@")[0]
        sisa = bagian[1] if len(bagian) > 1 else ""

        if perintah in ("/start", "/help", "/bantuan"):
            kirim_pesan(token, chat_id, BANTUAN, thread)
            continue

        if perintah == "/id":
            judul = (msg.get("chat") or {}).get("title") or "chat pribadi"
            baris = [f"📍 <b>Lokasi pesan ini</b>\n",
                     f"Grup: {judul}\n\n",
                     f"<b>TELEGRAM_CHAT_ID</b>\n<code>{chat_id}</code>\n\n"]
            if thread:
                baris.append(f"<b>TELEGRAM_TOPIC_ID</b>\n<code>{thread}</code>\n\n"
                             f"Pakai dua angka ini sebagai Secrets di repo bot "
                             f"yang kamu mau kirim ke topik ini.")
            else:
                baris.append("<b>TELEGRAM_TOPIC_ID</b>\n(tidak ada — ini topik "
                             "General atau chat biasa)\n\n"
                             "Kosongkan secret TELEGRAM_TOPIC_ID untuk mengirim "
                             "ke sini. Ketik /id di dalam topik lain untuk "
                             "mendapat nomor topik itu.")
            kirim_pesan(token, chat_id, "".join(baris), thread)
            continue

        if perintah == "/stok":
            if not source:
                kirim_pesan(token, chat_id,
                            "⚠️ Secret <code>SOURCE_REPO</code> belum diisi "
                            "di repo pengintai, jadi gudang tidak bisa dibaca.",
                            thread)
                continue
            paket, st = baca_gudang(pat, source)
            if paket is None:
                kirim_pesan(token, chat_id,
                            f"⚠️ Gagal membaca gudang (status {st}). "
                            f"Cek SOURCE_REPO dan izin GH_PAT.", thread)
            else:
                for bagian_teks in potong(teks_stok(paket)):
                    kirim_pesan(token, chat_id, bagian_teks, thread)
            continue

        if perintah in PERINTAH:
            topic_id = urai_nomor(sisa)
            if sisa and not topic_id:
                kirim_pesan(token, chat_id,
                            f"⚠️ <code>{sisa}</code> bukan nomor topik. "
                            f"Contoh benar: <code>{perintah} 3</code>", thread)
                continue
            for k in PERINTAH[perintah]:
                tugas.append((k, topic_id, chat_id, thread))
            continue

        kirim_pesan(token, chat_id,
                    f"Perintah <code>{perintah}</code> tidak dikenal.\n\n"
                    + BANTUAN, thread)

    # buang duplikat persona, jaga urutan
    unik, lihat = [], set()
    for k, tid, c, th in tugas:
        if k not in lihat:
            lihat.add(k)
            unik.append((k, tid, c, th))

    for kode, topic_id, chat_id, thread in unik:
        repo = os.environ.get(TUJUAN[kode], "").strip()
        if not repo:
            print(f"!! Secret {TUJUAN[kode]} belum diisi.")
            if chat_id:
                kirim_pesan(token, chat_id,
                            f"⚠️ Secret <code>{TUJUAN[kode]}</code> belum "
                            f"diisi di repo pengintai.", thread)
            continue

        ok, st, info = suruh_kerja(pat, repo, kode, topic_id)
        print(f"{'OK  ' if ok else 'GAGAL'} {kode}"
              f"{' ' + topic_id if topic_id else ''} -> {repo} (status {st})")
        if chat_id:
            if ok:
                dari = f" dari topik {topic_id.upper()}" if topic_id else ""
                kirim_pesan(token, chat_id,
                            f"✅ {LABEL[kode]}{dari} sedang dibuat. "
                            f"Hasilnya masuk dalam 1–3 menit.", thread)
            else:
                kirim_pesan(token, chat_id,
                            f"⚠️ Gagal menyuruh <code>{repo}</code> bekerja "
                            f"(status {st}). Cek izin GH_PAT dan nama repo.\n"
                            f"{str(info)[:200]}", thread)

    # tandai sudah diproses supaya tidak terbaca lagi
    tg(token, "getUpdates", {"offset": terakhir + 1, "timeout": 0})
    print("Selesai.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
