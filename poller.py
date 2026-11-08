# -*- coding: utf-8 -*-
"""
PENGINTAI PERINTAH — dipasang di repo 'adhd-poller' (Public).

Tiap beberapa menit dia melihat apakah kamu menekan tombol atau mengetik
perintah di Telegram, lalu menyuruh repo yang tepat bekerja.

Dia memantau DUA bot:
  materi_bot  -> perintah /stok, /anak, /semua, /ide, /nilai, dll
  ADHD_bot    -> tombol Setujui / Tolak pada artikel

Tidak ada rahasia di dalam file ini. Semua token ada di Settings > Secrets,
dan Secrets tetap tersembunyi meski repo ini Public.

File ini hanya memakai pustaka bawaan Python.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

API_TG = "https://api.telegram.org/bot{token}/{metode}"

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

# Alasan penolakan. Harus sama dengan yang ada di memori.py
ALASAN = [
    ("gaya", "✍️ Gaya bahasa belum pas"),
    ("contoh", "🔍 Kurang contoh konkret"),
    ("solusi", "🛠 Solusinya lemah"),
    ("dangkal", "📉 Terlalu umum"),
]

BANTUAN = (
    "<b>Perintah yang tersedia</b>\n\n"
    "<b>Bikin tulisan</b>\n"
    "/umum — artikel ADHD umum\n"
    "/anak — narasi sudut pandang anak\n"
    "/orangtua — narasi sudut pandang orang tua\n"
    "/video — script video\n"
    "/semua — keempatnya sekaligus\n\n"
    "<b>Lihat isi</b>\n"
    "/stok — daftar topik di gudang bahan\n"
    "/nilai — rapor: berapa disetujui, apa yang sering ditolak\n"
    "/ide — kumpulan ide aplikasi yang sudah terpanen\n"
    "/id — tampilkan CHAT ID dan TOPIC ID di sini\n\n"
    "Tambahkan nomor topik untuk memilih bahan:\n"
    "<code>/anak 3</code> · <code>/semua 2</code>\n\n"
    "Artikel dari ADHD_bot punya tombol Setujui / Tolak. "
    "Semakin sering dinilai, semakin cocok tulisannya dengan seleramu."
)


# --------------------------------------------------------------------
# DASAR
# --------------------------------------------------------------------
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


def kirim_pesan(token, chat_id, teks, thread=None, tombol=None):
    data = {"chat_id": chat_id, "text": teks, "parse_mode": "HTML",
            "disable_web_page_preview": True}
    if thread:
        data["message_thread_id"] = thread
    if tombol:
        data["reply_markup"] = tombol
    tg(token, "sendMessage", data)


def potong(teks, batas=3800):
    hasil, buf = [], ""
    for b in teks.split("\n"):
        if len(buf) + len(b) + 1 > batas:
            hasil.append(buf)
            buf = ""
        buf += b + "\n"
    if buf.strip():
        hasil.append(buf)
    return hasil or [teks]


def kirim_panjang(token, chat_id, teks, thread=None):
    for bagian in potong(teks):
        kirim_pesan(token, chat_id, bagian, thread)


# --------------------------------------------------------------------
# BACA FILE DI REPO LAIN
# --------------------------------------------------------------------
def baca_file_repo(pat, repo, jalur):
    status, hasil = minta(
        f"https://api.github.com/repos/{repo}/contents/{jalur}",
        headers={"Authorization": f"Bearer {pat}",
                 "Accept": "application/vnd.github.raw",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "adhd-poller"})
    return (hasil, 200) if status == 200 else (None, status)


def teks_stok(paket):
    topics = paket.get("topics") or []
    if not topics:
        return ("🗂 <b>Gudang masih kosong.</b>\n\nJalankan 'Jembatan Topik' "
                "di repo materi_bot untuk mengisinya.")
    baris = [f"🗂 <b>GUDANG BAHAN</b> — {len(topics)} topik\n"
             f"Diperbarui: {paket.get('tanggal_wib', '-')}\n"]
    for t in topics:
        tag = " · ".join((t.get("gejala") or [])[:2]) or "Umum ADHD"
        baris.append(f"\n<b>{t.get('id', '?').upper()}</b> · "
                     f"{t.get('judul', '')[:95]}\n"
                     f"   🏷 {tag} · skor {t.get('skor', '-')}\n")
    baris.append("\nContoh pakai: <code>/anak 3</code>")
    return "".join(baris)


def teks_nilai(mem):
    catatan = mem.get("catatan", [])
    if not catatan:
        return ("📊 <b>RAPOR AGENT</b>\n\nBelum ada naskah yang dicatat. "
                "Ketik /umum untuk membuat yang pertama.")

    dinilai = [c for c in catatan if c.get("status") in ("disetujui", "ditolak")]
    setuju = [c for c in dinilai if c["status"] == "disetujui"]
    tunggu = [c for c in catatan if c.get("status") == "menunggu"]

    baris = [f"📊 <b>RAPOR AGENT</b>\n\n",
             f"Total naskah  : {len(catatan)}\n",
             f"Disetujui     : {len(setuju)}\n",
             f"Ditolak       : {len(dinilai) - len(setuju)}\n",
             f"Belum dinilai : {len(tunggu)}\n"]

    if dinilai:
        laju = round(100 * len(setuju) / len(dinilai))
        baris.append(f"\n<b>Tingkat setuju keseluruhan: {laju}%</b>\n")

    # bandingkan 10 penilaian pertama vs 10 terakhir
    if len(dinilai) >= 10:
        awal = dinilai[:5]
        akhir = dinilai[-5:]
        la = round(100 * sum(1 for x in awal if x["status"] == "disetujui") / len(awal))
        lb = round(100 * sum(1 for x in akhir if x["status"] == "disetujui") / len(akhir))
        arah = "naik ⬆️" if lb > la else ("turun ⬇️" if lb < la else "datar ➡️")
        baris.append(f"5 pertama {la}% → 5 terakhir {lb}%  ({arah})\n")
    else:
        kurang = 10 - len(dinilai)
        baris.append(f"\n<i>Butuh {kurang} penilaian lagi sebelum tren bisa "
                     f"dibaca.</i>\n")

    alasan = {}
    for c in dinilai:
        if c["status"] == "ditolak" and c.get("alasan"):
            alasan[c["alasan"]] = alasan.get(c["alasan"], 0) + 1
    if alasan:
        peta = dict(ALASAN)
        baris.append("\n<b>Alasan penolakan terbanyak</b>\n")
        for a, n in sorted(alasan.items(), key=lambda x: -x[1]):
            baris.append(f"  {peta.get(a, a)} — {n}x\n")
        baris.append("\nSemua ini sudah dipakai sebagai larangan di tulisan "
                     "berikutnya.\n")

    baris.append(f"\n💡 Ide aplikasi terkumpul: {len(mem.get('ide_aplikasi', []))} "
                 f"(ketik /ide)")
    return "".join(baris)


def teks_ide(mem):
    ide = mem.get("ide_aplikasi", [])
    if not ide:
        return ("💡 <b>IDE APLIKASI</b>\n\nBelum ada. Ide dipanen otomatis "
                "setiap kali ADHD_bot menulis artikel.")
    baris = [f"💡 <b>IDE APLIKASI</b> — {len(ide)} terkumpul\n",
             "<i>Dipanen otomatis dari tiap artikel. Bahan mentah untuk "
             "aplikasi yang kamu rencanakan.</i>\n"]
    for i, x in enumerate(reversed(ide[-25:]), 1):
        baris.append(f"\n{i}. {x.get('ide', '')}\n")
    return "".join(baris)


# --------------------------------------------------------------------
# SURUH REPO BEKERJA
# --------------------------------------------------------------------
def dispatch(pat, repo, event_type, payload):
    status, hasil = minta(
        f"https://api.github.com/repos/{repo}/dispatches",
        {"event_type": event_type, "client_payload": payload},
        headers={"Authorization": f"Bearer {pat}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "adhd-poller"})
    return status == 204, status, hasil


def tombol_alasan(id_catatan):
    baris = [[{"text": label, "callback_data": f"fbr:{kode}:{id_catatan}"}]
             for kode, label in ALASAN]
    baris.append([{"text": "↩️ Batal, setujui saja",
                   "callback_data": f"fb:ok:{id_catatan}"}])
    return {"inline_keyboard": baris}


def urai_nomor(sisa):
    m = re.match(r"^t?(\d{1,2})$", (sisa or "").strip())
    return f"t{int(m.group(1))}" if m else None


# --------------------------------------------------------------------
# PROSES SATU BOT
# --------------------------------------------------------------------
def proses(nama_bot, token, pat, source, tugas):
    status, hasil = tg(token, "getUpdates",
                       {"timeout": 0,
                        "allowed_updates": ["callback_query", "message"]})
    if status != 200 or not hasil.get("ok"):
        print(f"!! [{nama_bot}] gagal baca Telegram (status {status}): "
              f"{str(hasil)[:200]}")
        return False

    updates = hasil.get("result", [])
    print(f"[{nama_bot}] {len(updates)} pesan/tombol menunggu diproses.")
    if not updates:
        return True

    terakhir = 0
    for u in updates:
        terakhir = max(terakhir, u.get("update_id", 0))

        # ---------- TOMBOL ----------
        cb = u.get("callback_query")
        if cb:
            data = cb.get("data") or ""
            pesan_cb = cb.get("message") or {}
            chat_id = (pesan_cb.get("chat") or {}).get("id")
            thread = pesan_cb.get("message_thread_id")
            tg(token, "answerCallbackQuery",
               {"callback_query_id": cb.get("id"), "text": "Diproses…"})

            # Setujui / Tolak
            if data.startswith("fb:"):
                _, verdict, id_catatan = (data.split(":", 2) + ["", ""])[:3]
                if verdict == "ok":
                    tugas["nilai"].append(
                        {"fb_id": id_catatan, "fb_status": "ok",
                         "fb_alasan": "", "chat": chat_id, "thread": thread,
                         "token": token})
                elif verdict == "no":
                    kirim_pesan(token, chat_id,
                                f"❌ Menolak <code>{id_catatan}</code>.\n"
                                f"Kenapa? Pilih satu — jawabanmu jadi larangan "
                                f"untuk tulisan berikutnya.",
                                thread, tombol_alasan(id_catatan))
                continue

            # Alasan penolakan
            if data.startswith("fbr:"):
                _, kode, id_catatan = (data.split(":", 2) + ["", ""])[:3]
                tugas["nilai"].append(
                    {"fb_id": id_catatan, "fb_status": "no",
                     "fb_alasan": kode, "chat": chat_id, "thread": thread,
                     "token": token})
                continue

            # Tombol bikin script
            if data.startswith("gen:"):
                pilih = data.split(":", 1)[1]
                kodenya = (list(TUJUAN) if pilih == "semua"
                           else ([pilih] if pilih in TUJUAN else []))
                for k in kodenya:
                    tugas["script"].append((k, None, chat_id, thread, token))
            continue

        # ---------- PERINTAH ----------
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
            b = [f"📍 <b>Lokasi pesan ini</b>\nGrup: {judul}\n\n",
                 f"<b>TELEGRAM_CHAT_ID</b>\n<code>{chat_id}</code>\n\n"]
            if thread:
                b.append(f"<b>TELEGRAM_TOPIC_ID</b>\n<code>{thread}</code>")
            else:
                b.append("<b>TELEGRAM_TOPIC_ID</b>\n(tidak ada — ini topik "
                         "General atau chat biasa)")
            kirim_pesan(token, chat_id, "".join(b), thread)
            continue

        if perintah == "/stok":
            if not source:
                kirim_pesan(token, chat_id, "⚠️ Secret <code>SOURCE_REPO</code> "
                            "belum diisi di repo pengintai.", thread)
                continue
            paket, st = baca_file_repo(pat, source, "shared/topics.json")
            if paket is None:
                kirim_pesan(token, chat_id, f"⚠️ Gagal membaca gudang "
                            f"(status {st}). Cek SOURCE_REPO dan GH_PAT.", thread)
            else:
                kirim_panjang(token, chat_id, teks_stok(paket), thread)
            continue

        if perintah in ("/nilai", "/ide"):
            repo_umum = os.environ.get("REPO_UMUM", "").strip()
            if not repo_umum:
                kirim_pesan(token, chat_id, "⚠️ Secret <code>REPO_UMUM</code> "
                            "belum diisi di repo pengintai.", thread)
                continue
            mem, st = baca_file_repo(pat, repo_umum, "data/memory.json")
            if mem is None:
                pesan = ("📊 Ingatan belum terbentuk. Buat satu artikel dengan "
                         "/umum, nilai hasilnya, lalu coba lagi."
                         if st == 404 else
                         f"⚠️ Gagal membaca ingatan (status {st}). "
                         f"Cek REPO_UMUM dan GH_PAT.")
                kirim_pesan(token, chat_id, pesan, thread)
            else:
                isi = teks_nilai(mem) if perintah == "/nilai" else teks_ide(mem)
                kirim_panjang(token, chat_id, isi, thread)
            continue

        if perintah in PERINTAH:
            topic_id = urai_nomor(sisa)
            if sisa and not topic_id:
                kirim_pesan(token, chat_id,
                            f"⚠️ <code>{sisa}</code> bukan nomor topik. "
                            f"Contoh benar: <code>{perintah} 3</code>", thread)
                continue
            for k in PERINTAH[perintah]:
                tugas["script"].append((k, topic_id, chat_id, thread, token))
            continue

        kirim_pesan(token, chat_id,
                    f"Perintah <code>{perintah}</code> tidak dikenal.\n\n"
                    + BANTUAN, thread)

    tg(token, "getUpdates", {"offset": terakhir + 1, "timeout": 0})
    return True


# --------------------------------------------------------------------
# UTAMA
# --------------------------------------------------------------------
def main():
    pat = os.environ.get("GH_PAT", "").strip()
    source = os.environ.get("SOURCE_REPO", "").strip()
    if not pat:
        print("!! GH_PAT belum diisi di Secrets.")
        return 1

    bot = []
    t1 = os.environ.get("MATERI_BOT_TOKEN", "").strip()
    t2 = os.environ.get("ADHD_BOT_TOKEN", "").strip()
    if t1:
        bot.append(("materi_bot", t1))
    if t2:
        bot.append(("ADHD_bot", t2))
    if not bot:
        print("!! MATERI_BOT_TOKEN belum diisi di Secrets.")
        return 1
    if not t2:
        print("   (ADHD_BOT_TOKEN kosong — tombol Setujui/Tolak tidak dipantau)")

    tugas = {"script": [], "nilai": []}
    sehat = True
    for nama, token in bot:
        if not proses(nama, token, pat, source, tugas):
            sehat = False

    # --- kirim tugas pembuatan script (buang persona kembar) ---
    unik, lihat = [], set()
    for k, tid, c, th, tok in tugas["script"]:
        if k not in lihat:
            lihat.add(k)
            unik.append((k, tid, c, th, tok))

    for kode, topic_id, chat_id, thread, tok in unik:
        repo = os.environ.get(TUJUAN[kode], "").strip()
        if not repo:
            print(f"!! Secret {TUJUAN[kode]} belum diisi.")
            if chat_id:
                kirim_pesan(tok, chat_id, f"⚠️ Secret "
                            f"<code>{TUJUAN[kode]}</code> belum diisi.", thread)
            continue
        muatan = {"persona": kode}
        if topic_id:
            muatan["topic_id"] = topic_id
        ok, st, info = dispatch(pat, repo, "buat_script", muatan)
        print(f"{'OK  ' if ok else 'GAGAL'} script {kode}"
              f"{' ' + topic_id if topic_id else ''} -> {repo} ({st})")
        if chat_id:
            if ok:
                dari = f" dari topik {topic_id.upper()}" if topic_id else ""
                kirim_pesan(tok, chat_id, f"✅ {LABEL[kode]}{dari} sedang "
                            f"dibuat. Hasilnya masuk 1–3 menit.", thread)
            else:
                kirim_pesan(tok, chat_id, f"⚠️ Gagal menyuruh "
                            f"<code>{repo}</code> bekerja (status {st}). "
                            f"Cek izin GH_PAT.\n{str(info)[:180]}", thread)

    # --- kirim tugas penilaian (naskah terakhir yang menang kalau kembar) ---
    per_naskah = {}
    for t in tugas["nilai"]:
        per_naskah[t["fb_id"]] = t

    repo_umum = os.environ.get("REPO_UMUM", "").strip()
    for t in per_naskah.values():
        if not repo_umum:
            print("!! REPO_UMUM belum diisi, penilaian tidak bisa dicatat.")
            break
        ok, st, info = dispatch(pat, repo_umum, "simpan_penilaian",
                                {"fb_id": t["fb_id"],
                                 "fb_status": t["fb_status"],
                                 "fb_alasan": t["fb_alasan"]})
        print(f"{'OK  ' if ok else 'GAGAL'} nilai {t['fb_id']}="
              f"{t['fb_status']}/{t['fb_alasan'] or '-'} -> {repo_umum} ({st})")
        if t["chat"] and not ok:
            kirim_pesan(t["token"], t["chat"],
                        f"⚠️ Penilaian gagal dicatat (status {st}). "
                        f"Cek izin GH_PAT.\n{str(info)[:180]}", t["thread"])

    print("Selesai.")
    return 0 if sehat else 1


if __name__ == "__main__":
    sys.exit(main())
