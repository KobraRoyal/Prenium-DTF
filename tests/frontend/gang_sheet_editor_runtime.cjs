const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class ClassList {
  add() {}
  remove() {}
  toggle() { return false; }
  contains() { return false; }
}

class Element {
  constructor(selector = '') {
    this.selector = selector;
    this.attributes = {};
    this.children = [];
    this.classList = new ClassList();
    this.dataset = {};
    this.hidden = false;
    this.style = {};
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.clientHeight = 600;
    this.clientWidth = 600;
    this.offsetHeight = 20;
    this.offsetWidth = 60;
    this.scrollHeight = 600;
    this.scrollWidth = 600;
    this.listeners = new Map();
  }
  addEventListener(name, handler) { this.listeners.set(name, handler); }
  append(...nodes) { this.children.push(...nodes); }
  blur() {}
  closest(selector) { return selector === 'label' ? new Element('label') : null; }
  focus() { this.focused = true; }
  getAttribute(name) { return this.attributes[name] ?? null; }
  getBoundingClientRect() { return {left: 0, top: 0, right: 600, bottom: 600, width: 600, height: 600}; }
  hasPointerCapture() { return false; }
  matches(selector) { return selector.split(',').some((part) => part.trim() === this.selector); }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  remove() {}
  removeAttribute(name) { delete this.attributes[name]; }
  replaceChildren(...nodes) { this.children = nodes; }
  scrollTo() {}
  setAttribute(name, value) { this.attributes[name] = String(value); }
}

class Input extends Element {}
class Button extends Element {}
class Anchor extends Element {}

const initialState = {
  revision: 7,
  status: 'draft',
  width_mm: 580,
  height_mm: 300,
  minimum_height_mm: 100,
  maximum_height_mm: 1000,
  height_step_mm: 10,
  margin_mm: 0,
  spacing_mm: 0,
  spacing_x_mm: 0,
  spacing_y_mm: 0,
  unit_price_eur: 10,
  estimated_price_eur: 1.74,
  surface_sqm: 0.174,
  issues: [],
  preflight: {revision: 7, fingerprint: 'quality-r7', requires_acknowledgement: false, blocking: [], warnings: []},
  text_fonts: [],
  items: [{
    public_id: 'item-a',
    asset_version_public_id: '11111111-1111-4111-8111-111111111111',
    asset_name: 'Visuel A',
    kind: 'visual',
    x_mm: 20,
    y_mm: 20,
    width_mm: 100,
    height_mm: 50,
    rotation: 0,
    layout_group_id: null,
    quality: {source_ratio: 2, source_width_px: 1200, source_height_px: 600, recommended_dpi: 300},
  }],
};

const elements = new Map();
const elementFor = (selector) => {
  if (!elements.has(selector)) {
    const Klass = selector.includes('input') || selector.includes('spacing') || selector.includes('quantity') || selector.includes('csrf')
      ? Input
      : selector.includes('create-order') ? Anchor : Button;
    elements.set(selector, new Klass(selector));
  }
  return elements.get(selector);
};
const root = new Element('[data-gang-sheet-editor]');
root.dataset = {
  canEdit: 'true',
  layoutUrl: '/layout/',
  stateUrl: '/state/',
  actionUrlTemplate: '/actions/ACTION/',
  itemUrlTemplate: '/items/00000000-0000-0000-0000-000000000000/ACTION/',
  batchDeleteUrl: '/items/delete/',
};
root.querySelector = elementFor;
root.querySelectorAll = () => [];
elementFor('[data-csrf]').value = 'csrf-token';
elementFor('[data-lock-ratio]').checked = true;
const uploadForm = elementFor('.gang-asset-modal-form');
const uploadDialog = elementFor('#gang-asset-dialog');
const uploadControls = [
  elementFor('[data-dialog-close]'),
  elementFor('[data-batch-picker]'),
  elementFor('[data-configurator-submit]'),
];
uploadForm.closest = (selector) => selector === 'dialog' ? uploadDialog : null;
uploadForm.querySelector = elementFor;
uploadForm.querySelectorAll = (selector) => selector.includes('[data-dialog-close]') ? uploadControls : [];
uploadForm.reset = () => { uploadForm.wasReset = true; };

const initialNode = {textContent: JSON.stringify(initialState)};
const document = {
  activeElement: null,
  body: new Element('body'),
  createElement: (tag) => tag === 'input' ? new Input(tag) : tag === 'button' ? new Button(tag) : new Element(tag),
  createElementNS: (_namespace, tag) => new Element(tag),
  getElementById: (id) => id === 'gang-sheet-initial-state' ? initialNode : null,
  querySelector: (selector) => selector === '[data-gang-sheet-editor]' ? root : null,
};

const timers = [];
const toasts = [];
let fetchHandler = async () => { throw new Error('Unexpected fetch'); };
const window = {
  __gangSheetEditorTestHooks: {},
  addEventListener() {},
  clearTimeout() {},
  location: {origin: 'https://example.test', pathname: '/studio/', assign() {}},
  matchMedia: () => ({matches: false}),
  preniumToast: (message, type) => toasts.push({message, type}),
  requestAnimationFrame: (callback) => { callback(); return 1; },
  setTimeout: (callback, delay) => { timers.push({callback, delay}); return timers.length; },
};

const context = vm.createContext({
  console,
  document,
  window,
  fetch: (...args) => fetchHandler(...args),
  FormData,
  URL,
  Element,
  HTMLElement: Element,
  HTMLInputElement: Input,
  HTMLButtonElement: Button,
  HTMLAnchorElement: Anchor,
  HTMLImageElement: Element,
  Node: Element,
  requestAnimationFrame: window.requestAnimationFrame,
  structuredClone,
});
const source = fs.readFileSync(
  path.join(__dirname, '../../backend/static_src/js/gang-sheet-editor.js'),
  'utf8',
);
const hookPoint = '  syncSpacingControls();\n  setMobilePanel("canvas");';
assert.equal(source.split(hookPoint).length, 2, 'editor test hook point must remain unique');
const instrumentedSource = source.replace(hookPoint, `
  Object.assign(window.__gangSheetEditorTestHooks, {
    canResizeItem,
    calculateSnapForMove,
    changeSelectedMetric,
    clampSelectedOnSheet: () => clampItemOnSheet(selected()),
    clampMoveDelta,
    confirmComposition,
    constrainResizedItemOnSheet,
    getState: () => JSON.parse(JSON.stringify(state)),
    isDirty: () => dirty,
    moveSelectedBy: (deltaX, deltaY) => {
      const items = selectedItems();
      const starts = new Map(items.map((item) => [item.public_id, {x: item.x_mm, y: item.y_mm}]));
      const clamped = clampMoveDelta(items, starts, deltaX, deltaY);
      translateItemsBy(items, clamped.deltaX, clamped.deltaY);
      render();
      return clamped;
    },
    rotateSelected,
    render,
    renderItemQuality,
    qualityApproved,
    resizeItemFromPointer,
    saveLayout,
    setUploadFormBusy,
    showImportForm,
    select: (publicIds) => {
      selectedIds = new Set(publicIds);
      selectedId = publicIds.at(-1) || null;
    },
    setState: (nextState) => {
      state = JSON.parse(JSON.stringify(nextState));
      setDirty(false);
      acceptedPreflightFingerprint = "";
    },
    textMaxWidthMm,
  });
${hookPoint}`);
vm.runInContext(instrumentedSource, context);
const hooks = window.__gangSheetEditorTestHooks;

function response(payload, ok = true) {
  return {ok, json: async () => payload};
}

async function runNextTimer() {
  const timer = timers.shift();
  assert.ok(timer, 'a polling timer should be scheduled');
  await timer.callback();
  await new Promise((resolve) => setImmediate(resolve));
}

(async () => {
  hooks.select(['item-a']);

  const width = elementFor('[data-input-width]');
  const original = hooks.getState().items[0];
  for (const invalid of ['', '0', '-2', 'Infinity']) {
    width.value = invalid;
    assert.equal(hooks.changeSelectedMetric('width_mm', width), false);
    assert.equal(hooks.getState().items[0].width_mm, original.width_mm);
    assert.equal(width.value, 10);
  }
  assert.equal(hooks.isDirty(), false);
  assert.match(toasts.at(-1).message, /valeur précédente/);

  const invalidRatioState = hooks.getState();
  invalidRatioState.items[0].height_mm = 0;
  hooks.setState(invalidRatioState);
  hooks.select(['item-a']);
  width.value = '12';
  assert.equal(hooks.changeSelectedMetric('width_mm', width), false);
  assert.equal(hooks.getState().items[0].width_mm, original.width_mm);
  assert.match(toasts.at(-1).message, /proportions actuelles sont invalides/);

  hooks.setState(initialState);
  hooks.select(['item-a']);
  width.value = '12';
  assert.equal(hooks.changeSelectedMetric('width_mm', width), true);
  assert.equal(hooks.getState().items[0].width_mm, 120);
  assert.equal(hooks.isDirty(), true);
  let saveCalls = 0;
  fetchHandler = async (url) => {
    assert.equal(url, '/layout/');
    saveCalls += 1;
    return response({
      ok: false,
      error: {code: 'STALE_REVISION', message: 'Révision obsolète', revision: 8},
    }, false);
  };
  await assert.rejects(hooks.saveLayout(), /brouillon est conservé/);
  assert.equal(saveCalls, 1, 'a stale snapshot must never be submitted twice');
  assert.equal(hooks.getState().revision, 7);
  assert.equal(hooks.getState().items[0].width_mm, 120);
  assert.equal(hooks.isDirty(), true);

  hooks.setState(initialState);
  hooks.select(['item-a']);
  timers.length = 0;
  const calls = [];
  let stateReads = 0;
  fetchHandler = async (url, options = {}) => {
    calls.push({url, method: options.method || 'GET'});
    if (url === '/layout/') {
      return response({
        ok: true, revision: 8, height_mm: 300, surface_sqm: 0.174,
        estimated_price_eur: 1.74, issues: [],
      });
    }
    if (url === '/actions/render/') return response({ok: true, message: 'Rendu lancé'});
    if (url === '/actions/validate/') return response({ok: true, message: 'Composition validée'});
    if (url === '/state/') {
      stateReads += 1;
      if (stateReads === 1) throw new Error('GET temporarily unavailable');
      const status = stateReads === 2 ? 'ready' : 'validated';
      return response({ok: true, sheet: {...initialState, status}});
    }
    throw new Error(`Unexpected URL ${url}`);
  };

  await hooks.confirmComposition();
  assert.equal(hooks.getState().status, 'rendering');
  assert.equal(calls.filter(({url}) => url === '/actions/render/').length, 1);
  assert.ok(timers.length > 0, 'polling survives the failed first state refresh');
  assert.match(toasts.at(-1).message, /reprendra automatiquement/);

  await runNextTimer();
  assert.equal(calls.filter(({url}) => url === '/actions/render/').length, 1);
  assert.equal(calls.filter(({url}) => url === '/actions/validate/').length, 1);
  assert.equal(hooks.getState().status, 'validated');
  assert.equal(stateReads, 3);

  const warningState = {...initialState, preflight: {...initialState.preflight,
    requires_acknowledgement: true,
    warnings: [{code: 'source_warning', message: '<script>source warning</script>', item_public_ids: ['item-a']}],
  }};
  hooks.setState(warningState);
  hooks.select(['item-a']);
  hooks.render();
  calls.length = 0;
  await hooks.confirmComposition();
  assert.equal(calls.length, 0, 'unaccepted warnings never launch rendering');
  assert.equal(elementFor('[data-preflight-issues]').children[0].textContent,
    '1 visuel — <script>source warning</script>', 'warnings are plain text, never HTML');
  const ack = elementFor('[data-preflight-ack]');
  ack.checked = true;
  ack.listeners.get('change')({target: ack});
  assert.equal(hooks.qualityApproved(), true);
  width.value = '14';
  hooks.changeSelectedMetric('width_mm', width);
  assert.equal(hooks.qualityApproved(), false, 'editing revokes the old acknowledgement');
  assert.equal(ack.checked, false);
  assert.equal(elementFor('[data-preflight-ack-field]').hidden, true);

  hooks.setState({...warningState, status: 'ready'});
  hooks.render();
  ack.checked = true;
  ack.listeners.get('change')({target: ack});
  let validatePayload;
  fetchHandler = async (url, options = {}) => {
    if (url === '/actions/validate/') {
      validatePayload = Object.fromEntries(options.body.entries());
      return response({ok: false, error: {code: 'STALE_PREFLIGHT', message: 'Actualisez',
        preflight: {...warningState.preflight, fingerprint: 'new-analysis'}}}, false);
    }
    throw new Error('unexpected request: ' + url);
  };
  await hooks.confirmComposition();
  assert.deepEqual(validatePayload, {expected_revision: '7', preflight_fingerprint: 'quality-r7', acknowledge_quality: 'true'});
  assert.equal(ack.checked, false, 'server-side stale analysis revokes acknowledgement');
  assert.equal(hooks.qualityApproved(), false);

  hooks.setState(initialState);
  hooks.select(['item-a']);
  elementFor('[data-lock-ratio]').checked = false;
  width.value = '14';
  hooks.changeSelectedMetric('width_mm', width);
  assert.equal(elementFor('[data-ratio-warning]').hidden, false);
  elementFor('[data-restore-ratio]').listeners.get('click')();
  assert.equal(hooks.getState().items[0].width_mm / hooks.getState().items[0].height_mm, 2);
  assert.equal(elementFor('[data-lock-ratio]').checked, true);
  hooks.renderItemQuality(hooks.getState().items[0]);
  assert.match(elementFor('[data-item-quality]').textContent, /218 DPI/);

  const groupState = {...initialState, items: [
    {...initialState.items[0], public_id: 'item-a', x_mm: 500, y_mm: 10, width_mm: 60, height_mm: 180},
    {...initialState.items[0], public_id: 'item-b', x_mm: 500, y_mm: 210, width_mm: 60, height_mm: 180},
  ]};
  hooks.setState(groupState);
  hooks.select(['item-a', 'item-b']);
  hooks.rotateSelected();
  const rotated = hooks.getState().items;
  const left = Math.min(...rotated.map((item) => item.x_mm));
  const right = Math.max(...rotated.map((item) => item.x_mm + item.height_mm));
  assert.ok(left >= 0 && right <= groupState.width_mm);
  assert.equal(rotated[1].x_mm - rotated[0].x_mm, 200, 'global translation preserves spacing');
  assert.equal(rotated[1].y_mm - rotated[0].y_mm, 0, 'global translation preserves group geometry');

  const groupedItem = {...initialState.items[0], layout_group_id: 'group-a'};
  assert.equal(hooks.canResizeItem(groupedItem), false, 'a grouped item must be dissociated before resize');
  assert.equal(hooks.canResizeItem({...groupedItem, layout_group_id: null}), true);
  hooks.setState({...initialState, items: [groupedItem]});
  root.querySelectorAll = (selector) => selector.includes('[data-add-asset]')
    ? [elementFor('[data-add-asset]')]
    : [];
  hooks.render();
  root.querySelectorAll = () => [];
  assert.equal(elementFor('[data-auto-place]').disabled, true, 'auto-place cannot break a persisted group');
  assert.match(elementFor('[data-auto-place]').title, /Dissociez les groupes/);
  assert.equal(elementFor('[data-add-asset]').disabled, true, 'gallery placement cannot fail after a group exists');
  assert.match(elementFor('[data-add-asset]').title, /Dissociez les groupes/);
  hooks.select(['item-a']);
  const groupedWidth = hooks.getState().items[0].width_mm;
  width.value = '14';
  assert.equal(hooks.changeSelectedMetric('width_mm', width), false, 'isolating a group member cannot resize it');
  assert.equal(hooks.getState().items[0].width_mm, groupedWidth);
  hooks.renderItemQuality(hooks.getState().items[0]);
  assert.equal(elementFor('[data-restore-ratio]').disabled, true, 'ratio restore cannot resize a group member');

  const marginState = {...initialState, margin_mm: 25, items: [
    {...initialState.items[0], public_id: 'item-a', x_mm: 0, y_mm: 0},
    {...initialState.items[0], public_id: 'item-b', x_mm: 480, y_mm: 250},
  ]};
  hooks.setState(marginState);
  hooks.render();
  assert.equal(hooks.getState().issues.length, 0, 'the complete sheet remains printable when margin_mm is non-zero');
  assert.equal(hooks.getState().height_mm, 300, 'margin_mm does not add a hidden strip below the printed content');
  assert.equal(hooks.textMaxWidthMm({...marginState.items[1], kind: 'text'}), 100,
    'text can use the complete remaining width up to the right edge');

  const snapItem = {...initialState.items[0], x_mm: 2, y_mm: 2};
  hooks.setState({...initialState, margin_mm: 25, items: [snapItem]});
  const snapStarts = new Map([[snapItem.public_id, {x: 2, y: 2}]]);
  const edgeSnap = hooks.calculateSnapForMove([snapItem], snapStarts, 0, 0);
  assert.deepEqual([edgeSnap.deltaX, edgeSnap.deltaY], [-2, -2],
    'edge snapping targets zero instead of margin_mm');

  const clampState = {...initialState, margin_mm: 25, items: [
    {...initialState.items[0], x_mm: -20, y_mm: -30},
  ]};
  hooks.setState(clampState);
  hooks.select(['item-a']);
  hooks.clampSelectedOnSheet();
  let clamped = hooks.getState().items[0];
  assert.deepEqual([clamped.x_mm, clamped.y_mm], [0, 0], 'top and left clamp at zero');
  hooks.setState({...clampState, items: [{...clampState.items[0], x_mm: 900, y_mm: 900}]});
  hooks.select(['item-a']);
  hooks.clampSelectedOnSheet();
  clamped = hooks.getState().items[0];
  assert.deepEqual([clamped.x_mm, clamped.y_mm], [480, 250], 'right and bottom clamp at the exact sheet edges');

  const movingItems = [
    {...initialState.items[0], public_id: 'item-a', x_mm: 20, y_mm: 20},
    {...initialState.items[0], public_id: 'item-b', x_mm: 160, y_mm: 100},
  ];
  const movingStarts = new Map(movingItems.map((item) => [item.public_id, {x: item.x_mm, y: item.y_mm}]));
  const topLeftDelta = hooks.clampMoveDelta(movingItems, movingStarts, -999, -999);
  assert.deepEqual(
    [topLeftDelta.deltaX, topLeftDelta.deltaY],
    [-20, -20],
    'a grouped move stops at the top-left edges',
  );
  const bottomRightDelta = hooks.clampMoveDelta(movingItems, movingStarts, 999, 999);
  assert.deepEqual(
    [bottomRightDelta.deltaX, bottomRightDelta.deltaY],
    [320, 850],
    'a grouped move stops at the right and maximum roll edges without changing its geometry',
  );

  hooks.setState(initialState);
  hooks.select(['item-a']);
  hooks.moveSelectedBy(0, 500);
  assert.equal(hooks.getState().items[0].y_mm, 520);
  assert.equal(hooks.getState().height_mm, 570,
    'dragging below the current bottom dynamically extends the roll to the visual bottom');
  const maximumMove = hooks.moveSelectedBy(0, 999);
  assert.equal(maximumMove.deltaY, 430, 'the next drag is clamped at maximum_height_mm');
  assert.equal(hooks.getState().items[0].y_mm + hooks.getState().items[0].height_mm, 1000);
  assert.equal(hooks.getState().height_mm, 1000, 'the roll never extends beyond maximum_height_mm');

  const resizeFromCorner = (corner, deltaX, deltaY) => {
    const item = {...initialState.items[0], x_mm: 20, y_mm: 20};
    const start = {x: item.x_mm, y: item.y_mm, width: item.width_mm, height: item.height_mm};
    hooks.resizeItemFromPointer(item, {start, deltaX, deltaY, lockRatio: false, corner});
    hooks.constrainResizedItemOnSheet(item, {start, corner, lockRatio: false});
    return item;
  };
  const northWest = resizeFromCorner('nw', -999, -999);
  assert.deepEqual([northWest.x_mm, northWest.y_mm], [0, 0]);
  const northEast = resizeFromCorner('ne', 999, -999);
  assert.deepEqual([northEast.x_mm + northEast.width_mm, northEast.y_mm], [580, 0]);
  const southEast = resizeFromCorner('se', 999, 999);
  assert.deepEqual([southEast.x_mm + southEast.width_mm, southEast.y_mm + southEast.height_mm], [580, 1000]);
  const southWest = resizeFromCorner('sw', -999, 999);
  assert.deepEqual([southWest.x_mm, southWest.y_mm + southWest.height_mm], [0, 1000]);
  const quarterTurn = {...initialState.items[0], x_mm: 20, y_mm: 20, rotation: 90};
  const quarterStart = {x: 20, y: 20, width: 100, height: 50};
  hooks.resizeItemFromPointer(quarterTurn, {
    start: quarterStart, deltaX: 999, deltaY: 999, lockRatio: false, corner: 'se',
  });
  hooks.constrainResizedItemOnSheet(quarterTurn, {start: quarterStart, corner: 'se', lockRatio: false});
  assert.deepEqual(
    [quarterTurn.x_mm + quarterTurn.height_mm, quarterTurn.y_mm + quarterTurn.width_mm],
    [580, 1000],
    'a quarter-turned resize uses its effective width and height at the right-bottom edges',
  );

  hooks.setState({...initialState, margin_mm: 25});
  hooks.select(['item-a']);
  const xInput = elementFor('[data-input-x]');
  const yInput = elementFor('[data-input-y]');
  xInput.value = '-5';
  hooks.changeSelectedMetric('x_mm', xInput);
  assert.equal(hooks.getState().items[0].x_mm, 0, 'numeric x position clamps at the left edge');
  hooks.setState({...initialState, margin_mm: 25});
  hooks.select(['item-a']);
  yInput.value = '999';
  hooks.changeSelectedMetric('y_mm', yInput);
  assert.equal(hooks.getState().items[0].y_mm, 250, 'numeric y position clamps at the bottom edge');

  const ratioAtEdgesState = {...initialState, items: [{
    ...initialState.items[0], x_mm: 550, y_mm: 970, width_mm: 100, height_mm: 80,
  }]};
  hooks.setState(ratioAtEdgesState);
  hooks.select(['item-a']);
  elementFor('[data-restore-ratio]').listeners.get('click')();
  const ratioAtEdges = hooks.getState().items[0];
  assert.deepEqual(
    [ratioAtEdges.x_mm + ratioAtEdges.width_mm, ratioAtEdges.y_mm + ratioAtEdges.height_mm],
    [580, 1000],
    'ratio restoration returns the visual inside the exact right-bottom edges',
  );

  const bottomRotationState = {...initialState, margin_mm: 25, items: [
    {...initialState.items[0], public_id: 'item-a', x_mm: 10, y_mm: 900, width_mm: 180, height_mm: 60},
    {...initialState.items[0], public_id: 'item-b', x_mm: 210, y_mm: 900, width_mm: 180, height_mm: 60},
  ]};
  hooks.setState(bottomRotationState);
  hooks.select(['item-a', 'item-b']);
  hooks.rotateSelected();
  const bottomRotated = hooks.getState().items;
  assert.equal(Math.max(...bottomRotated.map((item) => item.y_mm + item.width_mm)), 1000,
    'group rotation stops exactly at the maximum bottom edge');
  assert.ok(Math.min(...bottomRotated.map((item) => item.x_mm)) >= 0,
    'group rotation cannot cross the left edge');

  const progress = elementFor('[data-batch-upload-progress]');
  hooks.setUploadFormBusy(true);
  assert.equal(uploadDialog.getAttribute('aria-busy'), 'true');
  assert.equal(progress.hidden, false, 'upload progress is announced while files are sent');
  assert.ok(uploadControls.every((control) => control.disabled), 'dialog actions are locked during upload');
  hooks.setUploadFormBusy(false);
  assert.equal(uploadDialog.getAttribute('aria-busy'), 'false');
  assert.equal(progress.hidden, true);
  assert.ok(uploadControls.every((control) => !control.disabled));

  const results = elementFor('[data-gang-import-results]');
  results.hidden = false;
  uploadForm.hidden = true;
  hooks.showImportForm({reset: true});
  assert.equal(uploadForm.hidden, false, 'new import reveals the upload form');
  assert.equal(results.hidden, true, 'new import hides the previous result panel');
  assert.equal(uploadForm.wasReset, true, 'new import resets the previous file selection');
  assert.equal(elementFor('[data-batch-picker]').focused, true, 'new import focuses the file picker');

  console.log('Gang sheet editor runtime: printable bounds, upload states and group behavior passed.');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
