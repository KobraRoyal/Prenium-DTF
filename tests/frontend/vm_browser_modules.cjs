'use strict';

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const STATIC_JS = path.join(__dirname, '../../backend/static_src/js');

const CHECKOUT_DELIVERY_IMPORT_RE =
  /import\s*\{[^}]*\}\s*from\s*["']\.\/checkout-delivery-fields\.js(?:\?[^"']*)?["']\s*;?\s*/m;

function collectExportNames(source) {
  const names = [];
  for (const match of source.matchAll(/^export\s+(?:async\s+)?function\s+(\w+)/gm)) {
    names.push(match[1]);
  }
  for (const match of source.matchAll(/^export\s+const\s+(\w+)/gm)) {
    names.push(match[1]);
  }
  return names;
}

function stripNamedExports(source) {
  return source
    .replace(/^export\s+(async\s+)?function\s+/gm, '$1function ')
    .replace(/^export\s+const\s+/gm, 'const ');
}

function loadCheckoutDeliveryFields(context) {
  const raw = fs.readFileSync(path.join(STATIC_JS, 'checkout-delivery-fields.js'), 'utf8');
  const names = collectExportNames(raw);
  const body = stripNamedExports(raw);
  const assign = `Object.assign(globalThis, { ${names.join(', ')} });`;
  vm.runInContext(`${body}\n${assign}`, context);
}

function prepareBrowserSource(source) {
  return source.replace(CHECKOUT_DELIVERY_IMPORT_RE, '');
}

function runBrowserScript(source, context) {
  loadCheckoutDeliveryFields(context);
  vm.runInContext(prepareBrowserSource(source), context);
}

module.exports = {
  STATIC_JS,
  loadCheckoutDeliveryFields,
  prepareBrowserSource,
  runBrowserScript,
};
