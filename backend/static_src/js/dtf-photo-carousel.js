/** Responsive photo navigation; the track remains natively scrollable without JS. */
export function initPhotoCarousel(root, reduced) {
  if (!root) return;
  const track = root.querySelector('[data-photo-track]');
  const photos = [...track.children];
  const previous = root.querySelector('[data-photo-previous]');
  const next = root.querySelector('[data-photo-next]');
  const counter = root.querySelector('[data-photo-counter]');
  const controls = root.querySelector('[data-photo-controls]');
  let first = 0, intended = null, frame = 0;
  const offset = (index) => photos[index].offsetLeft - photos[0].offsetLeft;
  const metrics = () => {
    const stride = photos.length > 1 ? offset(1) : track.clientWidth;
    const gap = parseFloat(getComputedStyle(track).columnGap) || 0;
    const visible = Math.max(1, Math.round((track.clientWidth + gap) / stride));
    return { visible, last: Math.max(0, photos.length - visible), stride };
  };
  const update = (index) => {
    const {visible, last} = metrics();
    first = Math.max(0, Math.min(index, last));
    previous.disabled = first === 0;
    next.disabled = first === last;
    counter.textContent = visible === 1 ? `${first + 1} / ${photos.length}` : `${first + 1}–${Math.min(first + visible, photos.length)} / ${photos.length}`;
  };
  const select = (index, instant = false) => {
    update(index);
    intended = first;
    track.scrollTo({left: offset(first), behavior: instant || reduced.matches ? 'instant' : 'smooth'});
    if (Math.abs(track.scrollLeft - offset(first)) < 1) intended = null;
  };
  previous.addEventListener('click', () => select(first - metrics().visible));
  next.addEventListener('click', () => select(first + metrics().visible));
  track.addEventListener('keydown', (event) => {
    if (event.target !== track) return;
    const {visible, last} = metrics();
    const destinations = {ArrowLeft: first - visible, ArrowRight: first + visible, Home: 0, End: last};
    if (!(event.key in destinations)) return;
    event.preventDefault();
    select(destinations[event.key]);
  });
  const release = () => { intended = null; };
  track.addEventListener('pointerdown', release, {passive: true});
  track.addEventListener('wheel', release, {passive: true});
  track.addEventListener('scroll', () => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      if (intended !== null) {
        if (Math.abs(track.scrollLeft - offset(intended)) < 1) intended = null;
        return;
      }
      update(Math.round(track.scrollLeft / metrics().stride));
    });
  }, {passive: true});
  if ('ResizeObserver' in window) new ResizeObserver(() => select(first, true)).observe(track);
  reduced.addEventListener('change', () => select(first, true));
  controls.hidden = false;
  update(0);
}
