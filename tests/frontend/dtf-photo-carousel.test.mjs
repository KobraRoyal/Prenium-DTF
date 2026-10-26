import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
const source = await readFile(new URL('../../backend/static_src/js/dtf-photo-carousel.js', import.meta.url), 'utf8');
const {initPhotoCarousel} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

function fixture(columns = 2, reduced = false) {
  class Element {
    listeners = new Map();
    addEventListener(name, callback) { this.listeners.set(name, callback); }
    fire(name, event = {}) { this.listeners.get(name)?.(event); }
  }
  const track = new Element(), previous = new Element(), next = new Element();
  const counter = {}, controls = {hidden: true}, media = new Element();
  media.matches = reduced;
  let count = columns, resize;
  const frames = [];
  track.clientWidth = 640;
  track.scrollLeft = 0;
  track.children = Array.from({length: 5}, (_, i) => ({get offsetLeft() { return i * ((track.clientWidth + 24) / count); }}));
  const bySelector = {'[data-photo-track]': track, '[data-photo-previous]': previous, '[data-photo-next]': next, '[data-photo-counter]': counter, '[data-photo-controls]': controls};
  const root = {querySelector: selector => bySelector[selector]};
  globalThis.getComputedStyle = () => ({columnGap: '24px'});
  globalThis.requestAnimationFrame = callback => { frames.push(callback); return frames.length; };
  globalThis.ResizeObserver = class { constructor(callback) { resize = callback; } observe() {} };
  globalThis.window = {ResizeObserver};
  track.scrollTo = options => { track.lastScroll = options; };
  initPhotoCarousel(root, media);
  const settle = () => {
    track.scrollLeft = track.lastScroll.left;
    track.fire('scroll');
    while (frames.length) frames.shift()();
  };
  const key = value => track.fire('keydown', {target: track, key: value, preventDefault() {}});
  return {track, previous, next, counter, controls, media, settle, key,
    resize(value) { count = value; resize(); settle(); },
    manual(index) { track.fire('pointerdown'); track.scrollLeft = track.children[index].offsetLeft; track.fire('scroll'); while (frames.length) frames.shift()(); },
  };
}

test('Five photographs remain reachable in pairs, including the final odd photograph', () => {
  const f = fixture();
  assert.equal(f.controls.hidden, false);
  assert.equal(f.counter.textContent, '1–2 / 5');
  assert.equal(f.previous.disabled, true);
  f.next.fire('click'); f.settle();
  assert.equal(f.counter.textContent, '3–4 / 5');
  f.next.fire('click'); f.settle();
  assert.equal(f.counter.textContent, '4–5 / 5');
  assert.equal(f.next.disabled, true);
  f.key('Home'); f.settle();
  assert.equal(f.counter.textContent, '1–2 / 5');
});

test('Keyboard and responsive changes preserve the visible photograph and valid bounds', () => {
  const f = fixture(1);
  f.key('End'); f.settle();
  assert.equal(f.counter.textContent, '5 / 5');
  f.resize(2);
  assert.equal(f.counter.textContent, '4–5 / 5');
  assert.equal(f.next.disabled, true);
  f.key('ArrowLeft'); f.settle();
  assert.equal(f.counter.textContent, '2–3 / 5');
  f.key('Home'); f.settle();
  assert.equal(f.previous.disabled, true);
});

test('Rapid navigation and manual scrolling do not leave stale counters', () => {
  const f = fixture();
  f.next.fire('click'); f.next.fire('click'); f.previous.fire('click'); f.settle();
  assert.equal(f.counter.textContent, '2–3 / 5');
  f.manual(0);
  assert.equal(f.counter.textContent, '1–2 / 5');
  assert.equal(f.previous.disabled, true);
});

test('Reduced motion makes both navigation and preference changes immediate', () => {
  const f = fixture(1, true);
  f.next.fire('click'); f.settle();
  assert.equal(f.track.lastScroll.behavior, 'instant');
  f.media.matches = false;
  f.next.fire('click'); f.settle();
  assert.equal(f.track.lastScroll.behavior, 'smooth');
  f.media.matches = true;
  f.media.fire('change'); f.settle();
  assert.equal(f.track.lastScroll.behavior, 'instant');
});
