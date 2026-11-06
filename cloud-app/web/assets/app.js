const $ = (id) => document.getElementById(id);
const state = { config: null, mode: 'photo', file: null, localUrl: null, job: null, submitting: false, timer: null, toastTimer: null, format: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'png' : 'gif' };
const initialIds = ['happy', 'ok', 'love', 'cry', 'tired', 'shock'];
const samples = [
  { id: 'happy', caption: '开心起飞' }, { id: 'ok', caption: '收到' },
  { id: 'love', caption: '比心心' }, { id: 'cry', caption: '委屈巴巴' },
  { id: 'tired', caption: '好困啊' }, { id: 'shock', caption: '震鲸' },
];
const terminal = new Set(['completed', 'failed', 'cancelled']);
let choiceInputs = [];

function toast(message) {
  clearTimeout(state.toastTimer);
  $('toast').textContent = message;
  $('toast').hidden = false;
  state.toastTimer = setTimeout(() => { $('toast').hidden = true; }, 4500);
}

async function api(path, options = {}) {
  let response;
  try { response = await fetch(path, { credentials: 'same-origin', ...options }); }
  catch { throw new Error('暂时无法连接云端服务，请检查网络后再试。'); }
  let body;
  try { body = await response.json(); }
  catch { throw new Error('服务返回了无法读取的响应，请稍后再试。'); }
  if (!response.ok) {
    const error = new Error(typeof body.detail === 'string' ? body.detail : '请求未完成，请检查输入。');
    error.status = response.status;
    throw error;
  }
  return body;
}

function selectedChoices() {
  return choiceInputs.filter((x) => x.check.checked).map((x) => ({ id: x.id, caption: x.caption.value.trim() }));
}

function options() {
  const expressions = selectedChoices();
  if (!expressions.length || expressions.length > 8) throw new Error('请选择 1–8 个表情。');
  if (expressions.some((x) => !x.caption || [...x.caption].length > 12)) throw new Error('每条文案需要 1–12 个字。');
  if (new Set(expressions.map((x) => x.caption)).size !== expressions.length) throw new Error('原项目要求每张表情的文案不同，请修改重复文案。');
  return {
    expressions,
    style: document.querySelector('input[name=style]:checked').value,
    ink: document.querySelector('input[name=ink]:checked').value,
    motion: $('motion').value,
    consent: $('consent').checked,
  };
}

function updateControls() {
  const busy = Boolean(state.job && !terminal.has(state.job.status)) || state.submitting;
  $('settings-fields').disabled = busy;
  $('demo-button').disabled = busy || !state.config;
  const selected = selectedChoices();
  $('selection-count').textContent = `${selected.length} / 8`;
  const configured = Boolean(state.config?.provider_configured);
  $('generate-button').disabled = busy || !state.config || !state.file || !selected.length || !$('consent').checked || (state.mode === 'photo' && !configured);
  $('generate-label').textContent = state.mode === 'atlas' ? '检查并导入图集' : '生成姿势图集';
  let hint;
  if (busy) hint = state.job?.status === 'review' ? '先在右侧检查图集，再继续导出。' : '正在处理，可在右侧查看当前阶段。';
  else if (!state.config) hint = '无法读取服务配置，请刷新页面重试。';
  else if (state.mode === 'photo' && !configured) hint = '图像服务待配置。可先体验示例或导入透明图集。';
  else if (!state.file) hint = state.mode === 'photo' ? '先上传一张照片，再开始制作。' : '按选中表情顺序导入透明 PNG 图集。';
  else if (!$('consent').checked) hint = '请先确认素材使用权与本次处理。';
  else hint = state.mode === 'photo' ? `本次发起 1 次图集编辑请求，费用以服务商账单为准。` : '仅在本服务处理，不调用图像模型。';
  $('generation-hint').textContent = hint;
  $('clear-button').hidden = !state.job;
}

function buildChoices(expressions) {
  const root = $('expression-options');
  root.replaceChildren();
  choiceInputs = [];
  for (const item of expressions) {
    const tile = document.createElement('div'); tile.className = 'expression-option';
    const label = document.createElement('label'); label.className = 'expression-label';
    const symbol = document.createElement('span'); symbol.className = 'expression-symbol'; symbol.textContent = item.emoji; symbol.ariaHidden = 'true';
    const name = document.createElement('span'); name.textContent = item.name;
    const check = document.createElement('input'); check.type = 'checkbox'; check.checked = initialIds.includes(item.id); check.setAttribute('aria-label', `选择${item.name}`);
    label.append(symbol, name, check);
    const caption = document.createElement('input'); caption.type = 'text'; caption.className = 'caption-input'; caption.value = item.caption; caption.maxLength = 12; caption.setAttribute('aria-label', `${item.name}的文案`); caption.autocomplete = 'off';
    tile.append(label, caption); root.append(tile);
    choiceInputs.push({ id: item.id, check, caption });
    check.addEventListener('change', () => {
      if (selectedChoices().length > 8) { check.checked = false; toast('一次最多制作 8 张表情，请先取消一个。'); }
      updateControls();
    });
    caption.addEventListener('input', updateControls);
  }
}

function clearFile() {
  if (state.localUrl) URL.revokeObjectURL(state.localUrl);
  state.file = null; state.localUrl = null;
  $('source-input').value = '';
  $('source-thumbnail').hidden = true;
  $('source-thumbnail').removeAttribute('src');
  $('choose-source').classList.remove('has-file');
  $('upload-title').textContent = state.mode === 'photo' ? '点击上传，或拖入照片' : '点击上传，或拖入透明图集';
  $('upload-hint').textContent = state.mode === 'photo' ? 'JPG / PNG / WebP · 最大 10 MB' : '真正透明的 PNG · 最大 10 MB';
}

async function chooseFile(file) {
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) return toast('图片最大 10 MB，请先压缩后上传。');
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) return toast('请选择 JPG、PNG 或 WebP 图片。');
  const url = URL.createObjectURL(file);
  const image = new Image(); image.src = url;
  try { await image.decode(); }
  catch { URL.revokeObjectURL(url); return toast('无法读取这张图片，请重新选择。'); }
  if (Math.min(image.width, image.height) < 128 || image.width * image.height > 24_000_000) {
    URL.revokeObjectURL(url); return toast('请使用宽高至少 128 像素、2400 万像素以内的图片。');
  }
  clearFile();
  state.file = file; state.localUrl = url;
  $('source-thumbnail').src = url; $('source-thumbnail').hidden = false;
  $('choose-source').classList.add('has-file');
  $('upload-title').textContent = file.name;
  $('upload-hint').textContent = `${image.width} × ${image.height} · ${(file.size / 1024 / 1024).toFixed(2)} MB · 点击重新选择`;
  updateControls();
}

function switchMode(mode) {
  state.mode = mode; clearFile();
  document.querySelectorAll('[data-source]').forEach((button) => {
    const active = button.dataset.source === mode;
    button.classList.toggle('selected', active); button.setAttribute('aria-pressed', String(active));
  });
  $('upload-hint').textContent = mode === 'photo' ? 'JPG / PNG / WebP · 最大 10 MB' : '真正透明的 PNG · 最大 10 MB';
  $('upload-tag').textContent = mode === 'photo' ? '一张清晰的单人正面照，效果更好' : '2 张用 2×1；3–4 张用 2×2；5–8 张用 4×2';
  $('local-note').textContent = mode === 'photo' ? '选择照片时仅在浏览器预览，点击生成后才上传。' : '按照选中表情的顺序排列，未用的格子保持透明。';
  $('consent-label').textContent = mode === 'photo' ? '我有权使用该照片，同意将它发送至已配置的图像服务生成图集，并承担相应 API 费用。' : '我有权使用该图集，同意在本服务中处理并导出。此流程不调用外部图像服务。';
  $('consent').checked = false;
  updateControls();
}

function openImage(title, src, downloads = []) {
  $('sticker-title').textContent = title;
  $('large-sticker').src = src; $('large-sticker').alt = title;
  const root = $('sticker-downloads'); root.replaceChildren();
  downloads.forEach(({ label, href }) => {
    const link = document.createElement('a'); link.className = 'secondary-button'; link.textContent = label; link.href = href; link.download = '';
    root.append(link);
  });
  $('sticker-dialog').showModal();
}

function renderStickers() {
  const completed = state.job?.status === 'completed';
  const list = completed ? state.job.results : samples;
  const root = $('sticker-grid'); root.replaceChildren();
  for (const [index, item] of list.entries()) {
    const card = document.createElement('button'); card.type = 'button'; card.className = `sticker-card ${completed ? '' : 'sample'} ${completed && state.job.options.style !== 'pixel' ? 'photo-style' : ''}`;
    const number = document.createElement('span'); number.className = 'sticker-number'; number.textContent = String(index + 1).padStart(2, '0');
    const expand = document.createElement('span'); expand.className = 'sticker-open'; expand.textContent = '↗'; expand.ariaHidden = 'true';
    const image = document.createElement('img');
    const src = completed ? item[`${state.format}_url`] : `/assets/samples/${item.id}.${state.format}`;
    image.src = src; image.alt = completed ? item.caption : `开源项目示例：${item.caption}`; image.loading = 'lazy'; image.width = completed && state.job.options.style !== 'pixel' ? 512 : 320; image.height = image.width;
    card.setAttribute('aria-label', `查看${completed ? '' : '开源示例：'}${item.caption}`);
    card.append(number, expand, image); root.append(card);
    card.addEventListener('click', () => openImage(item.caption, src, completed ? [{ label: '下载 GIF', href: item.gif_url }, { label: '下载 PNG', href: item.png_url }] : []));
  }
  document.querySelectorAll('[data-format]').forEach((button) => {
    const active = button.dataset.format === state.format;
    button.classList.toggle('selected', active); button.setAttribute('aria-pressed', String(active));
  });
}

function setSteps(step) {
  document.querySelectorAll('[data-step]').forEach((element) => {
    const n = Number(element.dataset.step);
    element.classList.toggle('current', n === step); element.classList.toggle('done', n < step);
    if (n === step) element.setAttribute('aria-current', 'step'); else element.removeAttribute('aria-current');
  });
}

function renderJob(job) {
  const previous = state.job;
  if (job && previous?.id !== job.id) {
    if (job.mode !== 'demo' && state.mode !== job.mode) switchMode(job.mode);
    if (job.mode === 'demo') clearFile();
    const selected = new Map(job.options.expressions.map((item) => [item.id, item.caption]));
    choiceInputs.forEach((item) => {
      item.check.checked = selected.has(item.id);
      if (selected.has(item.id)) item.caption.value = selected.get(item.id);
    });
    document.querySelectorAll('input[name=style]').forEach((input) => { input.checked = input.value === job.options.style; });
    document.querySelectorAll('input[name=ink]').forEach((input) => { input.checked = input.value === job.options.ink; });
    $('motion').value = job.options.motion;
  }
  state.job = job;
  $('error-box').hidden = !job?.error;
  $('error-box').textContent = job?.error || '';
  const waiting = job && ['generating', 'exporting'].includes(job.status);
  $('job-status').hidden = !waiting;
  if (waiting) {
    $('job-status-title').textContent = job.message;
    $('job-status-detail').textContent = job.status === 'exporting' ? '原项目正在合成 24 帧循环，随后执行透明度、边距和 ZIP 检查。' : job.mode === 'photo' ? `正在等待 ${state.config.provider_host} 返回图集。关闭页面不会撤回已发送的请求。` : '仅使用本地素材，不调用图像生成服务。';
  }
  const reviewing = job?.status === 'review';
  $('review-area').hidden = !reviewing;
  $('sticker-grid').hidden = Boolean(waiting || reviewing);
  if (reviewing && (previous?.status !== 'review' || previous?.id !== job.id)) {
    $('atlas-preview').src = job.atlas_url;
    $('review-checkbox').checked = false; $('export-button').disabled = true;
    $('cell-map').replaceChildren();
    job.options.expressions.forEach((item, i) => {
      const cell = document.createElement('span'); cell.textContent = `${i + 1} · ${item.caption}`; $('cell-map').append(cell);
    });
  }
  const completed = job?.status === 'completed';
  $('preview-badge').textContent = job ? job.mode === 'demo' ? '开源示例演示' : completed ? '你的表情包' : '当前任务' : '开源项目示例';
  $('preview-badge').classList.toggle('live', completed);
  $('canvas-label').textContent = completed ? `${job.results.length} 张 / ${job.verification.size} × ${job.verification.size}` : '透明背景 / 循环播放';
  $('gif-download').classList.toggle('disabled', !completed);
  $('gif-download').setAttribute('aria-disabled', String(!completed));
  $('png-download').hidden = !completed;
  if (completed) {
    $('gif-download').href = job.gif_zip_url; $('png-download').href = job.png_zip_url;
    $('download-heading').textContent = `${job.results.length} 个小情绪，已经准备好了`;
    $('download-description').textContent = 'GIF 合集包含原项目的离线动图浏览页。';
  } else {
    $('gif-download').removeAttribute('href'); $('png-download').removeAttribute('href');
    $('download-heading').textContent = '把你的情绪打包带走';
    $('download-description').textContent = '透明 GIF + 离线预览页，原项目一键导出。';
  }
  const caption = $('preview-caption').lastElementChild;
  if (!job || job.status === 'failed' || job.status === 'cancelled') caption.textContent = '以上为仓库自带的鲸鱼娘示例，与上传的照片无关。';
  else if (job.mode === 'demo') caption.textContent = '演示素材裁自仓库示例，由原脚本重新导出。未使用照片或调用 AI。';
  else if (completed) caption.textContent = '原项目技术校验通过。请预览后确认人物特征、表情和动效。';
  else if (reviewing) caption.textContent = '图集顺序不正确或人物特征有偏差时，请先修正素材。';
  else caption.textContent = '只有真实完成的结果会出现在这里，失败时不会用示例替代。';
  setSteps(reviewing ? 2 : completed || job?.status === 'exporting' ? 3 : 1);
  renderStickers(); updateControls();
}

function schedulePoll() {
  clearTimeout(state.timer);
  if (!state.job || !['generating', 'exporting'].includes(state.job.status)) return;
  const id = state.job.id;
  state.timer = setTimeout(async () => {
    try {
      const job = await api(`/api/jobs/${id}`);
      if (state.job?.id !== id) return;
      renderJob(job); schedulePoll();
    } catch (error) {
      if (state.job?.id !== id) return;
      if ([404, 410].includes(error.status)) { renderJob(null); toast('任务已过期或被清除，请重新制作。'); }
      else { $('job-status-detail').textContent = `${error.message} 网络恢复后继续查询，不会重复发送生成请求。`; schedulePoll(); }
    }
  }, 1200);
}

async function createPack(demo = false) {
  let opts;
  try { opts = options(); }
  catch (error) { return toast(error.message); }
  if (!demo && (!state.file || !opts.consent)) return toast('请先选择素材并确认本次处理。');
  state.submitting = true; updateControls();
  try {
    let job;
    if (demo) job = await api('/api/demo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(opts) });
    else {
      const body = new FormData(); body.append('options', JSON.stringify(opts)); body.append('mode', state.mode); body.append('source', state.file);
      job = await api('/api/jobs', { method: 'POST', body });
    }
    renderJob(job); schedulePoll();
    if (innerWidth < 781) $('preview-heading').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) { toast(error.message); }
  finally { state.submitting = false; updateControls(); }
}

async function initialize() {
  renderStickers(); updateControls();
  try {
    state.config = await api('/api/config');
    const configured = state.config.provider_configured;
    $('connection-label').textContent = configured ? '图像服务已配置' : '图像服务待配置';
    $('connection-button').classList.toggle('ready', configured);
    $('connection-summary').textContent = configured ? '服务端已配置图像服务，实际生成仍取决于模型权限、网络及额度。' : '暂未配置图像服务密钥。照片生成尚不能执行；示例和图集导出可直接使用。';
    $('provider-host').textContent = state.config.provider_host;
    $('provider-model').textContent = state.config.model;
    buildChoices(state.config.expressions);
    renderJob(state.config.latest_job); schedulePoll();
  } catch (error) {
    $('connection-label').textContent = '云端服务未连接';
    $('connection-summary').textContent = error.message;
    $('error-box').hidden = false; $('error-box').textContent = error.message;
    updateControls();
  }
}

$('choose-source').addEventListener('click', () => $('source-input').click());
$('source-input').addEventListener('change', (event) => chooseFile(event.target.files[0]));
['dragenter', 'dragover'].forEach((name) => $('choose-source').addEventListener(name, (event) => { event.preventDefault(); if (!$('settings-fields').disabled) $('choose-source').classList.add('dragging'); }));
['dragleave', 'drop'].forEach((name) => $('choose-source').addEventListener(name, (event) => { event.preventDefault(); $('choose-source').classList.remove('dragging'); }));
$('choose-source').addEventListener('drop', (event) => { if (!$('settings-fields').disabled) chooseFile(event.dataTransfer.files[0]); });
document.querySelectorAll('[data-source]').forEach((button) => button.addEventListener('click', () => switchMode(button.dataset.source)));
document.querySelectorAll('[data-format]').forEach((button) => button.addEventListener('click', () => { state.format = button.dataset.format; renderStickers(); }));
$('consent').addEventListener('change', updateControls);
$('generate-button').addEventListener('click', () => createPack(false));
$('demo-button').addEventListener('click', () => createPack(true));
$('connection-button').addEventListener('click', () => $('connection-dialog').showModal());
$('help-button').addEventListener('click', () => $('help-dialog').showModal());
document.querySelectorAll('dialog').forEach((dialog) => {
  dialog.querySelector('.close-dialog').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (event) => { if (event.target === dialog && (event.clientX < dialog.getBoundingClientRect().left || event.clientX > dialog.getBoundingClientRect().right || event.clientY < dialog.getBoundingClientRect().top || event.clientY > dialog.getBoundingClientRect().bottom)) dialog.close(); });
});
$('atlas-preview').addEventListener('click', () => openImage('完整透明图集 · 按顺序检查每一格', state.job.atlas_url));
$('review-checkbox').addEventListener('change', () => { $('export-button').disabled = !$('review-checkbox').checked; });
$('export-button').addEventListener('click', async () => {
  if (!state.job || !$('review-checkbox').checked) return;
  $('export-button').disabled = true;
  try {
    const job = await api(`/api/jobs/${state.job.id}/export`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reviewed: true }) });
    renderJob(job); schedulePoll();
  } catch (error) { toast(error.message); $('export-button').disabled = false; }
});
$('clear-button').addEventListener('click', async () => {
  $('clear-button').disabled = true;
  try {
    const wasGenerating = state.job?.status === 'generating' && state.job?.mode === 'photo';
    await api('/api/jobs', { method: 'DELETE' });
    clearTimeout(state.timer); clearFile(); renderJob(null);
    toast(wasGenerating ? '任务已清除；已经发送的图像请求仍可能计费。' : '任务与服务器素材已清除。');
  } catch (error) { toast(error.message); }
  finally { $('clear-button').disabled = false; }
});
window.addEventListener('beforeunload', () => { if (state.localUrl) URL.revokeObjectURL(state.localUrl); });
await initialize();
