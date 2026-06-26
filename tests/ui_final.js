#!/usr/bin/env node
/** Final verification: Debate Arena + Math Tutor after fixes
 * Version: 1.0.0 | 2026-06-26
 */
const { chromium } = require('playwright');
const BASE_URL = 'https://workbench.gronowski.cc';

async function main() {
  console.log('=== FINAL VERIFICATION ===\n');
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  // Login
  console.log('[1/3] Login...');
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(2000);
  // Try to log in - use text selectors
  const inputs = await page.$$('input');
  for (const inp of inputs) {
    const ph = await inp.getAttribute('placeholder');
    if (ph && ph.includes('email')) await inp.fill('admin');
    if (ph && ph.includes('password')) await inp.fill('admin123');
  }
  const signInBtn = await page.$('button:has-text("Sign In"):not(:has-text("API"))');
  if (signInBtn) {
    await signInBtn.click();
    await page.waitForTimeout(3000);
  }
  await page.waitForSelector('button:has-text("Sign out")', { timeout: 10000 }).catch(() => {});
  const loggedIn = await page.$('button:has-text("Sign out")');
  console.log('  Logged in:', !!loggedIn);

  // List tabs
  const tabs = await page.$$eval('nav button', els => els.map(e => e.textContent.trim()));
  console.log('  Tabs:', tabs.join(', '));

  // Test Debate Arena (fix verification)
  console.log('\n[2/3] Debate Arena...');
  try {
    await page.click('nav button:has-text("Debate Arena")');
    await page.waitForTimeout(2000);
    const roles = await page.$('#debate-roles');
    if (!roles) {
      console.log('  FAIL: No #debate-roles div');
      errors.push('Debate Arena: no #debate-roles');
    } else {
      const text = await roles.textContent();
      if (text.includes('Loading')) {
        console.log('  FAIL: Roles loading');
        errors.push('Debate Arena: roles still loading');
      } else {
        console.log('  OK: Roles loaded:', text.substring(0, 80).replace(/\n/g, ' '));
      }
    }
  } catch (e) {
    console.log('  FAIL:', e.message);
    errors.push('Debate Arena: ' + e.message);
  }

  // Test Math Tutor (fix verification)
  console.log('\n[3/3] Math Tutor...');
  try {
    const mathBtn = await page.$('nav button:has-text("Math Tutor")');
    if (!mathBtn) {
      console.log('  FAIL: Math Tutor tab not in navigation');
      errors.push('Math Tutor: tab not in navigation bar');
    } else {
      await mathBtn.click();
      await page.waitForTimeout(2000);
      console.log('  OK: Math Tutor tab exists and clicked');
    }
  } catch (e) {
    console.log('  FAIL:', e.message);
    errors.push('Math Tutor: ' + e.message);
  }

  // Results
  console.log('\n=== RESULTS ===');
  if (errors.length === 0) {
    console.log('✅ All fixes verified successfully!');
  } else {
    console.log(`❌ ${errors.length} issues:`);
    errors.forEach(e => console.log('   ', e));
  }
  if (errors.length > 0) {
    console.log('\nConsole errors:');
    errors.forEach(e => console.log('  ⚠', e));
  }
  await browser.close();
  process.exit(errors.length > 0 ? 1 : 0);
}
main().catch(e => { console.error(e); process.exit(1); });