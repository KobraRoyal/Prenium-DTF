import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(
  new URL("../../backend/static_src/js/dtf-motion-scene.js", import.meta.url), "utf8",
);
const { createMotionScene } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

function fixture(reduced = false) {
  const frames = new Map(), docListeners = new Map(), mediaListeners = new Map();
  let observer, nextFrame = 0, time = 6.4;
  const doc = {
    hidden: false,
    addEventListener: (key, fn) => docListeners.set(key, fn),
    removeEventListener: (key) => docListeners.delete(key),
  };
  const media = {
    matches: reduced,
    addEventListener: (key, fn) => mediaListeners.set(key, fn),
    removeEventListener: (key) => mediaListeners.delete(key),
  };
  const timeline = {
    killed: false,
    duration: () => 6.4,
    time(value) { if (value !== undefined) time = value; return time; },
    pause() {},
    kill() { this.killed = true; },
  };
  class Observer {
    constructor(callback) { this.callback = callback; observer = this; }
    observe() {}
    disconnect() { this.disconnected = true; }
  }
  const scene = createMotionScene(timeline, {
    element: { dataset: {} }, media, document: doc, Observer,
    requestFrame(fn) { frames.set(++nextFrame, fn); return nextFrame; },
    cancelFrame(id) { frames.delete(id); },
  });
  return {
    scene, timeline, doc, media, frames, docListeners, mediaListeners,
    visible(ratio = 1) {
      observer.callback([{ isIntersecting: ratio > 0, intersectionRatio: ratio }]);
    },
    tick(timestamp) {
      const pending = [...frames.values()];
      frames.clear();
      pending.forEach((callback) => callback(timestamp));
    },
    hidden(value) { doc.hidden = value; docListeners.get("visibilitychange")(); },
    reduce(value) { media.matches = value; mediaListeners.get("change")(); },
  };
}

test("A scene waits for a readable viewport, then finishes once and stays still", () => {
  const f = fixture();
  f.visible(0.01);
  assert.equal(f.scene.state, "idle");
  assert.equal(f.frames.size, 0);
  f.visible(0.3);
  assert.equal(f.scene.state, "playing");
  f.tick(0);
  f.tick(7000);
  assert.equal(f.timeline.time(), 6.4);
  assert.equal(f.scene.state, "complete");
  assert.equal(f.frames.size, 0);
  f.visible(0);
  f.visible(1);
  assert.equal(f.frames.size, 0);
});

test("Offscreen and hidden time is excluded; resuming does not jump", () => {
  const f = fixture();
  f.visible();
  f.tick(0);
  f.tick(1000);
  f.visible(0);
  assert.equal(f.scene.state, "paused");
  assert.equal(f.frames.size, 0);
  f.visible();
  f.tick(20000);
  assert.equal(f.timeline.time(), 1);
  f.tick(20500);
  assert.equal(f.timeline.time(), 1.5);
  f.hidden(true);
  assert.equal(f.frames.size, 0);
  f.hidden(false);
  f.tick(99000);
  assert.equal(f.timeline.time(), 1.5);
});

test("User pause persists on reentry and rapid replay never multiplies clocks", () => {
  const f = fixture();
  f.visible();
  f.tick(0);
  f.tick(500);
  f.scene.toggle();
  f.visible(0);
  f.visible();
  assert.equal(f.frames.size, 0);
  assert.equal(f.timeline.time(), 0.5);
  f.scene.toggle();
  assert.equal(f.frames.size, 1);
  f.scene.restart();
  f.scene.restart();
  assert.equal(f.frames.size, 1);
  assert.equal(f.timeline.time(), 0);
});

test("A manual mode interrupts autoplay permanently until explicit replay", () => {
  const f = fixture();
  f.visible();
  f.scene.settle();
  f.visible(0);
  f.visible();
  assert.equal(f.scene.state, "complete");
  assert.equal(f.frames.size, 0);
  f.scene.toggle();
  assert.equal(f.scene.state, "playing");
  assert.equal(f.timeline.time(), 0);
});

test("Reduced motion prevents autoplay and resolves an in-flight scene", () => {
  const initial = fixture(true);
  initial.visible();
  initial.scene.restart();
  assert.equal(initial.frames.size, 0);
  assert.equal(initial.timeline.time(), 6.4);
  const f = fixture();
  f.visible();
  f.tick(0);
  f.tick(500);
  f.reduce(true);
  assert.equal(f.frames.size, 0);
  assert.equal(f.timeline.time(), 6.4);
  f.reduce(false);
  f.visible();
  assert.equal(f.scene.state, "complete");
});

test("Destroy releases the observer, clock and preference listeners", () => {
  const f = fixture();
  f.visible();
  f.scene.destroy();
  assert.equal(f.frames.size, 0);
  assert.equal(f.docListeners.size, 0);
  assert.equal(f.mediaListeners.size, 0);
  assert.equal(f.timeline.killed, true);
});
