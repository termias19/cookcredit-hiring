import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const source=path=>readFileSync(new URL(path,import.meta.url),'utf8');

test('public Home discovery is static, canonical and linked once in the sitemap',()=>{
  const page=source('../../public-site/home/index.html');
  assert.match(page,/<title>Cooking and cleaning at home in Georgia/);
  assert.match(page,/<meta name="robots" content="index,follow/);
  assert.match(page,/<link rel="canonical" href="https:\/\/cookcredit.com\/home\/">/);
  assert.match(page,/<h1[^>]*>Good food/);
  assert.match(page,/href="https:\/\/cookcredit-home.web.app\/#callback"/);
  assert.doesNotMatch(page,/<script|eassefa@|683|home_payment_id|quoteId/);
  assert.equal((source('../../public-site/sitemap.xml').match(/https:\/\/cookcredit.com\/home\//g)||[]).length,1);
  assert.equal((source('../../public-site/index.html').match(/href="\/home\/">Help at home/g)||[]).length,2);
});

test('discovery reuses one Home stylesheet and photo source with stable content fingerprints',()=>{
  const page=source('../../public-site/home/index.html');
  const css=readFileSync(new URL('../home/style.css',import.meta.url)).toString().replaceAll('\r\n','\n');
  const cssHash=createHash('sha256').update(css).digest('hex').slice(0,12);
  const photoHash=createHash('sha256').update(readFileSync(new URL('../home/public/assets/cooking-visit.jpg',import.meta.url))).digest('hex').slice(0,12);
  assert.ok(page.includes('/home/style.css?v='+cssHash));
  assert.ok(page.includes('/home/cooking-visit-'+photoHash+'.jpg'));
  assert.match(source('../home/index.html'),/content="noindex,nofollow"/);
});
