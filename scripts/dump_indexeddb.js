/* Voicenotes IndexedDB dumper.
 *
 * Paste this whole file into the DevTools Console on https://voicenotes.com/app
 * while logged in. It reads every record from `VoicenotesDB.recordings` and
 * triggers a single download of `voicenotes-indexeddb-dump.json`.
 *
 * No network calls. No auth. Pure read of the local cache the SPA already uses.
 *
 * Output schema:
 *   {
 *     "exported_at": "2026-04-26T12:34:56.000Z",
 *     "source": "indexeddb:VoicenotesDB/recordings",
 *     "count": 6875,
 *     "records": [ <raw cache entry>, ... ]
 *   }
 *
 * Each cache entry is `{ id, message, recording, attachment, tags }`. The
 * `recording` field carries the full Voicenotes recording object (transcript,
 * metadata, creations, subnotes, ...). See FINDINGS.md for shape.
 */
(async () => {
  const DB_NAME = 'VoicenotesDB';
  const STORE = 'recordings';

  const open = (name) => new Promise((res, rej) => {
    const r = indexedDB.open(name);
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });

  console.log('[vn-dump] opening', DB_NAME);
  const db = await open(DB_NAME);
  if (!db.objectStoreNames.contains(STORE)) {
    console.error('[vn-dump] no store named', STORE, '— found:', [...db.objectStoreNames]);
    return;
  }

  const tx = db.transaction(STORE, 'readonly');
  const os = tx.objectStore(STORE);

  const total = await new Promise((res) => {
    const q = os.count(); q.onsuccess = () => res(q.result);
  });
  console.log('[vn-dump] expecting', total, 'records');

  const records = [];
  await new Promise((res, rej) => {
    const cur = os.openCursor();
    cur.onerror = () => rej(cur.error);
    cur.onsuccess = (e) => {
      const c = e.target.result;
      if (!c) { res(); return; }
      records.push(c.value);
      if (records.length % 500 === 0) console.log('[vn-dump] ...', records.length, '/', total);
      c.continue();
    };
  });
  db.close();

  const payload = {
    exported_at: new Date().toISOString(),
    source: `indexeddb:${DB_NAME}/${STORE}`,
    count: records.length,
    records,
  };

  const json = JSON.stringify(payload);
  const sizeMb = (json.length / 1e6).toFixed(1);
  console.log('[vn-dump] built payload:', records.length, 'records,', sizeMb, 'MB');

  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'voicenotes-indexeddb-dump.json';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 5000);

  console.log('[vn-dump] download triggered:', a.download);
})();
