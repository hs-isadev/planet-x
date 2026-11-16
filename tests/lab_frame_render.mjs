import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';
import {createContext, runInContext} from 'node:vm';

const viewer = readFileSync('web/observation-lab/app.js', 'utf8');
const extract = (name, next) => {
  const start = viewer.indexOf(`function ${name}(`);
  const stop = viewer.indexOf(`function ${next}(`, start + 1);
  assert.ok(start !== -1 && stop > start);
  return viewer.slice(start, stop);
};
const elements = new Map();
function element() {
  return {
    children: [], style: {setProperty() {}}, dataset: {},
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    setAttribute() {},
    showModal() { this.open = true; }
  };
}
const $ = id => {
  if (!elements.has(id)) elements.set(id, element());
  return elements.get(id);
};
const state = {loading: false, field: 'barnard'};
const context = createContext({
  state, $, document: {createElement: element}, entryList() {}, frameLabel: frame => frame.timestamp,
  updateLegend() {}, draw() {}, renderComparison() {}
});
runInContext(extract('setFrame', 'syncSwitcher') + extract('contextView', 'categoryBadge'), context);

const root = 'backend/data/spherex-seed';
const indexes = readdirSync(`${root}/featured-views`).filter(name => name.endsWith('.json'));
const json = path => JSON.parse(readFileSync(path, 'utf8'));
let tested = 0;
for (const name of indexes) {
  const {session} = json(`${root}/featured-views/${name}`);
  const manifest = json(`${root}/${session}/manifest.json`);
  state.session = manifest;
  manifest.frames.forEach((frame, index) => {
    context.setFrame(index);
    assert.equal($('fits-link').href, frame.fits_url);
    assert.equal($('context-button').hidden, !Array.isArray(frame.context) || !frame.context.length);
    tested++;
  });
}
assert.ok(tested > 0);
const [frame] = state.session.frames;
state.session.frames = [{...frame}];
delete state.session.frames[0].context;
context.setFrame(0);
assert.ok($('context-button').hidden);
context.contextView();
assert.ok(!$('context').open);
state.session.frames[0].context = [{detector: 3, jpeg: 'preview.jpg', source: 'observation.fits'}];
context.setFrame(0);
assert.equal($('context-button').hidden, false);
context.contextView();
assert.equal($('context-image').src, 'preview.jpg');
assert.equal($('context').open, true);
console.log(`PASS: ${tested} bundled observation frames and optional detector context.`);
