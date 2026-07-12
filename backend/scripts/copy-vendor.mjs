import { copyFile, mkdir } from "node:fs/promises";

const vendorDirectory = new URL("../static_src/vendor/", import.meta.url);
const fontDirectory = new URL("fonts/", vendorDirectory);
const pdfJsDirectory = new URL("pdfjs/", vendorDirectory);

await mkdir(vendorDirectory, { recursive: true });
await mkdir(fontDirectory, { recursive: true });
await mkdir(pdfJsDirectory, { recursive: true });
await Promise.all([
  copyFile(
    new URL("../node_modules/htmx.org/dist/htmx.min.js", import.meta.url),
    new URL("htmx-1.9.12.min.js", vendorDirectory),
  ),
  copyFile(
    new URL("../node_modules/alpinejs/dist/cdn.min.js", import.meta.url),
    new URL("alpinejs-3.14.3.min.js", vendorDirectory),
  ),
  copyFile(
    new URL(
      "../node_modules/@fontsource-variable/dm-sans/files/dm-sans-latin-wght-normal.woff2",
      import.meta.url,
    ),
    new URL("dm-sans-latin-wght-normal.woff2", fontDirectory),
  ),
  copyFile(
    new URL(
      "../node_modules/@fontsource-variable/space-grotesk/files/space-grotesk-latin-wght-normal.woff2",
      import.meta.url,
    ),
    new URL("space-grotesk-latin-wght-normal.woff2", fontDirectory),
  ),
  copyFile(
    new URL("../node_modules/pdfjs-dist/build/pdf.mjs", import.meta.url),
    new URL("pdf.js", pdfJsDirectory),
  ),
  copyFile(
    new URL("../node_modules/pdfjs-dist/build/pdf.worker.mjs", import.meta.url),
    new URL("pdf.worker.js", pdfJsDirectory),
  ),
]);
