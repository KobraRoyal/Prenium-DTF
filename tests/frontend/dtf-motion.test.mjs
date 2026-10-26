import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(
  new URL("../../backend/static_src/js/dtf-motion.js", import.meta.url),
  "utf8",
);
const { createMotion } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

function fixture(t, reduced = false) {
  const handlers = {},
    listeners = {};
  const prior = globalThis.document;
  const doc = {
    hidden: false,
    addEventListener: (name, handler) => {
      handlers[name] = handler;
    },
  };
  globalThis.document = doc;
  t.after(() => {
    if (prior === undefined) delete globalThis.document;
    else globalThis.document = prior;
  });
  const media = {
    matches: reduced,
    addEventListener: (name, handler) => {
      listeners[name] = handler;
    },
  };
  const animations = [];
  const element = {
    hidden: false,
    dataset: {},
    animate: (frames, options) => {
      const animation = {
        cancelled: false,
        cancel() {
          this.cancelled = true;
          this.oncancel?.();
        },
      };
      animations.push({ frames, options, animation });
      return animation;
    },
  };
  return {
    motion: createMotion(media),
    media,
    doc,
    element,
    animations,
    handlers,
    listeners,
  };
}

test("Reduced motion leaves content visible without starting an animation", (t) => {
  const f = fixture(t, true);
  f.motion.enter(f.element);
  assert.equal(f.animations.length, 0);
  assert.equal(f.element.hidden, false);
});

test("Rapid view changes replace the prior animation and settle on preference change", (t) => {
  const f = fixture(t);
  f.motion.enter(f.element, { kind: "panel" });
  f.motion.enter(f.element, { kind: "panel" });
  assert.equal(f.animations[0].animation.cancelled, true);
  assert.equal(f.animations[1].animation.cancelled, false);
  f.media.matches = true;
  f.listeners.change();
  assert.equal(f.animations[1].animation.cancelled, true);
  assert.equal(f.element.hidden, false);
});

test("A hidden tab stops motion and does not queue further animations", (t) => {
  const f = fixture(t);
  f.motion.enter(f.element);
  f.doc.hidden = true;
  f.handlers.visibilitychange();
  assert.equal(f.animations[0].animation.cancelled, true);
  f.motion.enter(f.element);
  assert.equal(f.animations.length, 1);
});
