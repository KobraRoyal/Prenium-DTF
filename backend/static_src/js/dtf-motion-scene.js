/* A web host for Hyperframes-style paused, seekable timelines.
   Only this clock advances the scene. Hidden time is never accumulated. */
export function createMotionScene(timeline, {
  element,
  media,
  onState = () => {},
  onStart = () => {},
  document: doc = document,
  requestFrame = requestAnimationFrame,
  cancelFrame = cancelAnimationFrame,
  Observer = globalThis.IntersectionObserver,
}) {
  const duration = timeline.duration();
  let visible = !Observer;
  let started = false;
  let complete = false;
  let requested = false;
  let frame = null;
  let previous = null;
  let state = "idle";

  function publish(next) {
    if (next === state) return;
    state = next;
    element.dataset.motionState = next;
    onState(next);
  }
  function stop() {
    if (frame !== null) cancelFrame(frame);
    frame = null;
    previous = null;
  }
  function step(timestamp) {
    frame = null;
    if (previous !== null) {
      const next = Math.min(duration, timeline.time() + (timestamp - previous) / 1000);
      timeline.time(next, false);
      if (next >= duration) {
        requested = false;
        complete = true;
        stop();
        publish("complete");
        return;
      }
    }
    previous = timestamp;
    frame = requestFrame(step);
  }
  function sync() {
    if (requested && visible && !doc.hidden && !media.matches) {
      publish("playing");
      if (frame === null) frame = requestFrame(step);
    } else {
      stop();
      publish(complete ? "complete" : started ? "paused" : "idle");
    }
  }
  function restart() {
    if (media.matches) return;
    stop();
    started = true;
    complete = false;
    requested = true;
    onStart();
    timeline.time(0, false);
    sync();
  }
  function toggle() {
    if (!started || complete) restart();
    else {
      requested = !requested;
      sync();
    }
  }
  function settle() {
    stop();
    started = true;
    complete = true;
    requested = false;
    timeline.time(duration, false);
    publish("complete");
  }
  function preference() {
    if (media.matches && !complete) settle();
    else sync();
  }
  const observer = Observer ? new Observer((entries) => {
    visible = entries.some((entry) => entry.isIntersecting && entry.intersectionRatio >= 0.25);
    if (visible && !started && !media.matches) restart();
    else sync();
  }, { threshold: 0.25 }) : null;

  timeline.pause();
  element.dataset.motionState = state;
  doc.addEventListener("visibilitychange", sync);
  media.addEventListener("change", preference);
  observer?.observe(element);
  if (!Observer && !media.matches) restart();

  return {
    restart,
    toggle,
    settle,
    get state() { return state; },
    destroy() {
      stop();
      observer?.disconnect();
      doc.removeEventListener("visibilitychange", sync);
      media.removeEventListener("change", preference);
      timeline.kill();
    },
  };
}
