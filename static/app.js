const $ = (id) => document.getElementById(id);
let jobId = null;
let segments = [];

/* ---------- range mode ---------- */
document.querySelectorAll('input[name=range]').forEach((r) => {
  r.addEventListener('change', () => {
    $('opt-first').hidden = r.value !== 'first';
    $('opt-range').hidden = r.value !== 'range';
  });
});

$('dur-chips').addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-dur]');
  if (!btn) return;
  $('duration').value = btn.dataset.dur;
  markChip();
});
$('duration').addEventListener('input', markChip);
function markChip() {
  document.querySelectorAll('#dur-chips button').forEach((b) =>
    b.classList.toggle('on', b.dataset.dur === $('duration').value.trim()));
}
markChip();

/* ---------- paste + preview ---------- */
$('paste').addEventListener('click', async () => {
  try {
    $('url').value = (await navigator.clipboard.readText()).trim();
    probe();
  } catch {
    $('url').focus();
  }
});
$('url').addEventListener('change', probe);
$('url').addEventListener('paste', () => setTimeout(probe, 50));

let probeToken = 0;
async function probe() {
  const url = $('url').value.trim();
  $('preview').hidden = true;
  if (!/^https?:\/\//.test(url)) return;
  const token = ++probeToken;
  try {
    const res = await fetch('/api/probe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, cookies_from_browser: $('cookies').value }),
    });
    const d = await res.json();
    if (token !== probeToken || d.error || !d.title) return;
    $('pv-title').textContent = d.title;
    const bits = [d.uploader, d.duration ? hms(d.duration) : null, d.extractor].filter(Boolean);
    $('pv-sub').textContent = bits.join(' · ');
    if (d.thumbnail) { $('pv-thumb').src = d.thumbnail; $('pv-thumb').hidden = false; }
    else { $('pv-thumb').hidden = true; }
    $('preview').hidden = false;
  } catch { /* preview is a nicety; never block on it */ }
}

function hms(s) {
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const p = (n) => String(n).padStart(2, '0');
  return h ? `${h}:${p(m)}:${p(sec)}` : `${m}:${p(sec)}`;
}

/* ---------- run ---------- */
$('go').addEventListener('click', start);
$('url').addEventListener('keydown', (e) => { if (e.key === 'Enter') start(); });

function start() {
  const mode = document.querySelector('input[name=range]:checked').value;
  const body = {
    url: $('url').value.trim(),
    range_mode: mode,
    duration: $('duration').value.trim(),
    start: $('start').value.trim(),
    end: $('end').value.trim(),
    accuracy: $('accuracy').value,
    lang: $('lang').value.trim(),
    translate: $('translate').checked,
    cookies_from_browser: $('cookies').value,
  };

  $('error').hidden = true;
  $('result').hidden = true;
  $('transcript').innerHTML = '';
  segments = [];
  $('go').disabled = true;
  $('go').textContent = 'Working…';
  $('progress').hidden = false;
  $('prog-msg').textContent = 'Starting…';
  $('prog-note').textContent = '';
  setStep(null);

  fetch('/api/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
    .then((r) => r.json())
    .then((d) => {
      if (d.error) return fail(d.error);
      jobId = d.job_id;
      listen(d.job_id);
    })
    .catch(() => fail('Could not reach the local server. Is it still running?'));
}

function listen(id) {
  const es = new EventSource(`/api/stream/${id}`);
  es.onmessage = (ev) => {
    const d = JSON.parse(ev.data);
    switch (d.stage) {
      case 'status':
      case 'download':
      case 'trim':
      case 'model':
      case 'transcribe':
        if (d.message) $('prog-msg').textContent = d.message;
        setStep(d.stage);
        if (d.stage === 'model') {
          $('prog-note').textContent =
            'First run with a model downloads it (up to ~1.5 GB). Later runs skip this.';
        } else if (d.stage === 'transcribe') {
          $('prog-note').textContent = 'Lines appear below as they are recognised.';
        }
        break;
      case 'language':
        $('prog-note').textContent =
          `Language: ${d.language} (${Math.round(d.confidence * 100)}% sure) · ` +
          `${hms(d.audio_duration)} of audio`;
        break;
      case 'segment':
        segments.push(d);
        $('result').hidden = false;
        addLine(d);
        break;
      case 'done':
        es.close();
        finish(d);
        break;
      case 'error':
        es.close();
        fail(d.message);
        break;
    }
  };
  es.onerror = () => { es.close(); reset(); };
}

function addLine(seg) {
  const box = $('transcript');
  const stamped = $('timestamps').checked;
  box.classList.toggle('plain', !stamped);
  const near = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
  if (stamped) {
    const el = document.createElement('div');
    el.className = 'line';
    const t = document.createElement('time');
    t.textContent = hms(seg.start);
    const p = document.createElement('span');
    p.textContent = seg.text;
    el.append(t, p);
    box.append(el);
  } else {
    box.textContent = (box.textContent ? box.textContent + ' ' : '') + seg.text;
  }
  if (near) box.scrollTop = box.scrollHeight;
}

/* re-render when the timestamp switch is flipped after the fact */
$('timestamps').addEventListener('change', () => {
  const box = $('transcript');
  box.innerHTML = '';
  box.textContent = '';
  segments.forEach(addLine);
});

function finish(d) {
  setStep('done');
  $('progress').hidden = true;
  $('stats').textContent =
    `${d.count} segment${d.count === 1 ? '' : 's'} · ${d.words} words`;
  reset();
}

function fail(msg) {
  $('progress').hidden = true;
  $('error').textContent = msg;
  $('error').hidden = false;
  reset();
}

function reset() {
  $('go').disabled = false;
  $('go').textContent = 'Transcribe';
}

const ORDER = ['download', 'model', 'transcribe', 'done'];
function setStep(stage) {
  const i = ORDER.indexOf(stage === 'trim' ? 'download' : stage);
  document.querySelectorAll('.step').forEach((el) => {
    const j = ORDER.indexOf(el.dataset.step);
    el.classList.toggle('active', j === i);
    el.classList.toggle('done', i >= 0 && j < i);
  });
}

/* ---------- output ---------- */
$('copy').addEventListener('click', async () => {
  const text = $('timestamps').checked
    ? segments.map((s) => `[${hms(s.start)}] ${s.text}`).join('\n')
    : segments.map((s) => s.text).join(' ');
  await navigator.clipboard.writeText(text);
  $('copy').textContent = 'Copied';
  setTimeout(() => ($('copy').textContent = 'Copy'), 1200);
});
$('dl-txt').addEventListener('click', () => {
  window.location = `/api/download/${jobId}.${$('timestamps').checked ? 'stamped' : 'txt'}`;
});
$('dl-srt').addEventListener('click', () => {
  window.location = `/api/download/${jobId}.srt`;
});
