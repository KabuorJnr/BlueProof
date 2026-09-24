import { chromium } from 'playwright';
const log = [];
const b = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium', args:['--no-sandbox'] });
const ctx = await b.newContext({ viewport:{width:390,height:844}, isMobile:true, hasTouch:true, deviceScaleFactor:2 });
const p = await ctx.newPage();
p.on('pageerror', e => log.push('PAGEERROR: ' + e.message));
p.on('console', m => { if (m.type()==='error' && !m.text().includes('ERR_INTERNET')) log.push('CONSOLE: '+m.text()); });

await p.goto('http://127.0.0.1:4191/', { waitUntil:'networkidle' });
await p.evaluate(() => localStorage.setItem('blueproof.apiBase','http://127.0.0.1:8011'));
await p.reload({ waitUntil:'networkidle' });
await p.waitForTimeout(1500);

log.push('title: ' + await p.title());
log.push('chip: ' + (await p.locator('.chip').textContent()).trim());
log.push('plot rows: ' + await p.locator('.item').count());
await p.screenshot({ path:'/tmp/bp-plots.png' });

await p.locator('.item').nth(1).click();
await p.waitForTimeout(800);
log.push('monitor heading: ' + await p.locator('h2').textContent());
log.push('protocol steps: ' + await p.locator('.step').count());

// jump to the evidence (close) shot, step index 2
await p.getByRole('button', { name:'Mbele' }).click();
await p.getByRole('button', { name:'Mbele' }).click();
await p.waitForTimeout(300);
log.push('current shot: ' + (await p.locator('.shotname').textContent()).trim());

await p.setInputFiles('input[type=file]', '/tmp/plot.jpg');
await p.waitForTimeout(1500);
log.push('thumbs after capture: ' + await p.locator('.thumbs img').count());
await p.screenshot({ path:'/tmp/bp-monitor.png' });

await p.getByRole('button', { name:/Wasilisha/ }).click();
await p.waitForTimeout(4000);
log.push('hash: ' + await p.evaluate(()=>location.hash));
log.push('verdict heading: ' + await p.locator('h2').textContent());
log.push('verdict lines: ' + await p.locator('.verdictline').count());
const lines = await p.locator('.verdictline').allTextContents();
log.push('verdict: ' + lines.map(s=>s.replace(/\s+/g,' ').trim()).join(' | '));
await p.screenshot({ path:'/tmp/bp-verdict.png' });

await p.getByRole('button', { name:/Pochi/ }).click();
await p.waitForTimeout(1500);
log.push('wallet tiles: ' + await p.locator('.stat').count());
await p.screenshot({ path:'/tmp/bp-wallet.png' });

await p.getByRole('button', { name:/Eneo/ }).click();
await p.waitForTimeout(1500);
log.push('site tiles: ' + await p.locator('.stat').count());
await p.getByRole('button', { name:/Sasisha picha za setilaiti/ }).click();
await p.waitForTimeout(4000);
log.push('after satellite refresh, tiles: ' + await p.locator('.stat b').allTextContents());
await p.screenshot({ path:'/tmp/bp-site.png' });

console.log(log.join('\n'));
await b.close();
