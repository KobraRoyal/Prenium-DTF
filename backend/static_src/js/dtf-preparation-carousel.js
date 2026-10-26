/** Native scroll keeps the complete photo story usable without JavaScript. */
export function initPreparationCarousel(root, reduced) {
  if (!root) return;
  const track = root.querySelector('[data-preparation-track]');
  const slides = [...root.querySelectorAll('[data-preparation-slide]')];
  const picks = [...root.querySelectorAll('[data-preparation-pick]')];
  const previous = root.querySelector('[data-preparation-prev]');
  const next = root.querySelector('[data-preparation-next]');
  const counter = root.querySelector('[data-preparation-counter]');
  let current = 0;
  let intended = null;
  let frame = 0;
  const offset = (index) => slides[index].offsetLeft - slides[0].offsetLeft;
  const update = (index) => {
    current = index;
    picks.forEach((pick, i) => pick.setAttribute('aria-pressed', String(i === index)));
    previous.disabled = index === 0;
    next.disabled = index === slides.length - 1;
    counter.textContent = `${index + 1} / ${slides.length}`;
  };
  const select = (index, instant = false) => {
    const target = Math.max(0, Math.min(index, slides.length - 1));
    intended = target;
    update(target);
    track.scrollTo({ left: offset(target), behavior: instant || reduced.matches ? 'instant' : 'smooth' });
    if (Math.abs(track.scrollLeft - offset(target)) < 1) intended = null;
  };
  previous.addEventListener('click', () => select(current - 1));
  next.addEventListener('click', () => select(current + 1));
  picks.forEach((pick, index) => pick.addEventListener('click', () => select(index)));
  track.addEventListener('keydown', (event) => {
    // Leave nested controls and editable content their own keyboard behavior.
    if (event.target !== track) return;
    const keys = { ArrowLeft: current - 1, ArrowRight: current + 1, Home: 0, End: slides.length - 1 };
    if (!(event.key in keys)) return;
    event.preventDefault();
    select(keys[event.key]);
  });
  const release = () => { intended = null; };
  track.addEventListener('pointerdown', release, { passive: true });
  track.addEventListener('wheel', release, { passive: true });
  track.addEventListener('scroll', () => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      if (intended !== null) {
        if (Math.abs(track.scrollLeft - offset(intended)) < 1) intended = null;
        return;
      }
      let nearest = 0;
      slides.forEach((slide, i) => {
        if (Math.abs(track.scrollLeft - offset(i)) < Math.abs(track.scrollLeft - offset(nearest))) nearest = i;
      });
      if (nearest !== current) update(nearest);
    });
  }, { passive: true });
  if ('ResizeObserver' in window) new ResizeObserver(() => select(current, true)).observe(track);
  reduced.addEventListener('change', () => select(current, true));
  root.querySelector('[data-preparation-controls]').hidden = false;
  update(0);
}
