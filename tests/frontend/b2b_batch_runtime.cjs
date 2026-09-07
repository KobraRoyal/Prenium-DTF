const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
class Element {
  constructor() { this.dataset = {}; this.attributes = {}; this.hidden = false; this.isConnected = true; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  closest() { return null; }
  matches() { return false; }
  setAttribute(k, v) { this.attributes[k] = v; }
  removeAttribute(k) { delete this.attributes[k]; }
}
class Input extends Element {
  constructor(name = '', value = '') { super(); this.name = name; this.value = value; this.type = 'text'; this.files = []; }
  setCustomValidity(value) { this.validationMessage = value; }
  dispatchEvent(event) { this.onchange?.(event); }
}
class Button extends Element {}
class Form extends Element {
  constructor() {
    super();
    this.classList = {add() {}, contains() { return false; }};
    this.submitCount = 0;
  }
  checkValidity() { return true; }
  requestSubmit() { this.submitCount += 1; }
}
class List extends Element {
  constructor() { super(); this.children = []; }
  replaceChildren() { this.children = []; }
  append(node) { this.children.push(node); }
}
class DataTransfer {
  constructor() { this.files = []; this.items = {add: (file) => this.files.push(file)}; }
}
const listeners = {};
const document = {
  body: null, readyState: 'loading', activeElement: null,
  addEventListener() {}, createElement: () => new Element(),
};
const ctx = vm.createContext({
  document, window: {}, Element, HTMLElement: Element, HTMLInputElement: Input,
  HTMLButtonElement: Button, HTMLFormElement: Form, HTMLUListElement: List,
  DataTransfer, Event: class { constructor(type) { this.type = type; } }, Node: Element,
  queueMicrotask, console,
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../../backend/static_src/js/b2b-configurator.js'), 'utf8'), ctx);
const root = new Element(), form = new Form(), input = new Input('file');
const error = new Element(), summary = new Element(), list = new List(), submit = new Button();
root.closest = () => form;
root.querySelector = (selector) => ({'[data-configurator-file-error]': error, '[data-selected-files-summary]': summary, '[data-selected-files-list]': list}[selector]);
root.matches = (selector) => selector === '[data-batch-upload]';
form.querySelector = () => submit;
input.required = true;
input.dataset = {maxFiles: '5', maxFileBytes: '20', maxTotalBytes: '60'};
const valid = () => ctx.validateConfiguratorFiles(root, input);
assert.equal(valid(), ''); assert.equal(submit.disabled, true);
input.files = Array.from({length: 5}, (_, i) => ({name: `visuel-${i}.png`, size: 10}));
assert.equal(valid(), ''); assert.equal(submit.disabled, false);
input.files.push({name: 'six.png', size: 1});
assert.match(valid(), /maximum 5/); assert.equal(submit.disabled, true);
input.files = [{name: 'grand.png', size: 21}];
assert.match(valid(), /grand.png/);
input.files = Array.from({length: 4}, () => ({name: 'lourd.png', size: 20}));
assert.match(valid(), /sélection dépasse/);
input.files = [{name: '<img src=x onerror=alert(1)>.png', size: 1}, {name: 'b.png', size: 1}];
ctx.updateSelectedFilesSummary(root, input);
assert.equal(list.children[0].textContent, input.files[0].name);
assert.equal(summary.textContent, '2 fichiers sélectionnés');
// The real drop handler transfers every File, then triggers normal validation.
document.body = {addEventListener: (name, handler) => (listeners[name] ??= []).push(handler)};
ctx.bindBatchUploadEvents();
const dropzone = new Element();
dropzone.closest = (selector) => selector === '[data-batch-upload]' ? root : dropzone;
dropzone.querySelector = () => input;
dropzone.classList = {remove() {}, add() {}};
input.onchange = valid;
const dropped = Array.from({length: 5}, (_, i) => ({name: `drop-${i}.png`, size: 1}));
let prevented = false;
listeners.drop[0]({target: dropzone, dataTransfer: {files: dropped}, preventDefault() { prevented = true; }});
assert.equal(prevented, true); assert.equal(input.files.length, 5); assert.equal(submit.disabled, false);
listeners.drop[0]({target: dropzone, dataTransfer: {files: [...dropped, dropped[0]]}, preventDefault() {}});
assert.match(input.validationMessage, /maximum 5/);
// The same selected batch submits itself as soon as the form is valid.
const autoForm = new Form(), autoInput = new Input('file');
autoInput.files = [{name: 'auto.png', size: 1}];
autoInput.closest = (selector) => selector === 'form[data-batch-auto-submit]' ? autoForm : null;
ctx.submitBatchUploadWhenReady(autoInput);
assert.equal(autoForm.submitCount, 1);
// A polling replacement restores all unsaved values, including hidden multicolor state.
const quantity = new Input('quantity', '12'), hex = new Input('support_color_hex', '#112233'), multi = new Input('support_color_multicolor', 'on');
const draftForm = new Form();
draftForm.dataset.orderProjectInlineItem = 'item-a';
draftForm.querySelectorAll = () => [quantity, hex, multi];
draftForm.matches = () => true;
ctx.rememberInlineProjectDraft(draftForm);
quantity.value = '1'; hex.value = ''; multi.value = '';
ctx.restoreInlineProjectDrafts(draftForm);
assert.equal(quantity.value, '12'); assert.equal(hex.value, '#112233'); assert.equal(multi.value, 'on');
ctx.xhr = {status: 400};
vm.runInContext("projectInlineRequests.set(xhr, {itemId:'item-a', values:projectInlineDrafts.get('item-a')})", ctx);
ctx.completeInlineProjectRequest(ctx.xhr);
assert.equal(vm.runInContext("projectInlineDrafts.has('item-a')", ctx), true);
ctx.xhr = {status: 200};
vm.runInContext("projectInlineRequests.set(xhr, {itemId:'item-a', values:projectInlineDrafts.get('item-a')})", ctx);
quantity.value = '13'; ctx.rememberInlineProjectDraft(draftForm);
ctx.completeInlineProjectRequest(ctx.xhr);
assert.equal(vm.runInContext("projectInlineDrafts.get('item-a').quantity", ctx), '13');
ctx.xhr = {status: 200};
vm.runInContext("projectInlineRequests.set(xhr, {itemId:'item-a', values:projectInlineDrafts.get('item-a')})", ctx);
ctx.completeInlineProjectRequest(ctx.xhr);
assert.equal(vm.runInContext("projectInlineDrafts.has('item-a')", ctx), false);
const poll = new Element(); poll.id = 'order-project-visuals-state';
quantity.closest = () => draftForm; quantity.matches = () => true;
document.activeElement = quantity;
assert.equal(ctx.projectAnalysisPollIsEditing(poll), true);
document.activeElement = new Button();
assert.equal(ctx.projectAnalysisPollIsEditing(poll), false);
console.log('Batch runtime: limits, drop, safe filenames, drafts and polling passed.');
