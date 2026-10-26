import assert from 'node:assert/strict';
import test from 'node:test';
import { replaceScript, replaceCss } from './singlefile.mjs';

test('inline script preserves module attributes and escapes HTML end tags', () => {
  const html = replaceScript('<script type="module" src="./app.js"></script>', 'app.js', 'const s="</script>";');
  assert.ok(html.includes('type="module"'));
  assert.ok(!html.includes('src='));
  assert.equal((html.match(/<\/script>/g) || []).length, 1);
});
test('inline stylesheet replaces generated asset link', () => {
  const html = replaceCss('<link rel="stylesheet" href="./style.css">', 'style.css', 'body{color:red}');
  assert.ok(html.includes('body{color:red}'));
  assert.ok(!html.includes('href='));
});
