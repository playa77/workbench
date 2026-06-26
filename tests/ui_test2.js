#!/usr/bin/env node
/** UI/UX Test Suite — Round 2: Debate Arena (fix verification) + Math Tutor
 * Version: 1.0.0 | 2026-06-26
 */

const { chromium } = require('playwright');
const fs = require('fs');

const BASE_URL = 'https://workbench.gronowski.cc';
const USERNAME = 'admin';
const PASSWORD = 'admin123';

async function main() {
  console.log('=== WORKBENCH UI TEST — ROUND 2 ===\n');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();

  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  const results = { passed: [], failed: [], notes: [] };

  // -- Login --
  console.log('[LOGIN]');
  await page.goto(BASE_URL, { waitUntil: 'load', timeout: 30000 });
  await page.waitForTimeout(3000);

  // Debug: print page title and URL
  console.log('  Page title:', await page.title());
  console.log('  URL:', await page.url());

  let signOutBtn = await page.$('button:has-text("Sign out")');
  if (signOutBtn) {
    console.log('  Already logged in.');
  } else {
    // Make sure the login form is visible
    const formVisible = await page.waitForSelector('input[placeholder="Enter your email or username"]', { timeout: 15000 }).catch(() => null);
    if (!formVisible) {
      // Dump body text for debugging
      const body = await page.textContent('body');
      console.error('  Login form not found. Body preview:', body.substring(0, 200));
      await browser.close();
      process.exit(1);
    }
    await page.fill('input[placeholder="Enter your email or username"]', USERNAME);
    await page.fill('input[placeholder="Enter your password"]', PASSWORD);
    await page.click('button:has-text("Sign In"):not(:has-text("API"))');
    await page.waitForTimeout(3000);

    signOutBtn = await page.$('button:has-text("Sign out")');
    if (!signOutBtn) {
      console.error('Login failed, aborting.');
      await browser.close();
      process.exit(1);
    }
    console.log('  Logged in.');
  }

  // -- Get list of tabs in nav --
  const tabButtons = await page.$$eval('nav button', els => els.map(e => e.textContent.trim()));
  console.log('  Tabs available:', tabButtons.join(', '));

  // == TEST: Debate Arena (re-test with fix) ==
  console.log('\n--- Debate Arena (re-test) ---');
  try {
    await page.click('nav button:has-text("Debate Arena")');
    await page.waitForTimeout(2000);

    // Check for JS syntax error rendering
    const debateError = await page.$('#debate-roles');
    if (!debateError) {
      console.error('  FAIL: Debate roles div not found');
      results.failed.push('Debate Arena: roles div missing');
    } else {
      const rolesText = await debateError.textContent();
      if (rolesText.includes('Failed') || rolesText.includes('Loading roles')) {
        console.error('  FAIL: Roles still failing to load:', rolesText.trim());
        results.failed.push('Debate Arena: roles load failed');
      } else {
        console.log('  OK: Roles rendered correctly');
        results.passed.push('Debate Arena');

        // Verify topic input
        const topic = await page.$('#debate-topic');
        if (topic) console.log('  OK: Topic input present');
      }
    }
  } catch (e) {
    console.error('  FAIL:', e.message);
    results.failed.push('Debate Arena: ' + e.message);
  }

  // == TEST: Math Tutor ==
  console.log('\n--- Math Tutor ---');
  try {
    const mathBtn = await page.$('nav button:has-text("Math Tutor")');
    if (!mathBtn) {
      console.log('  Math Tutor tab NOT in navigation.');
      results.notes.push('Math Tutor: tab not in navigation bar');
    } else {
      await mathBtn.click();
      await page.waitForTimeout(2000);
      console.log('  Tab clicked. Checking content...');

      // Look for form elements
      const chatInput = await page.$('input[placeholder*="message"], textarea[placeholder*="message"]');
      const structuredEl = await page.$('#math-interview, .math-wizard, [class*="math-interview"]');

      if (chatInput) {
        console.log('  OK: Chat input found');
        results.passed.push('Math Tutor');
      } else if (structuredEl) {
        console.log('  OK: Structured interview wizard found');
        results.passed.push('Math Tutor');
      } else {
        console.log('  WARN: No recognizable form elements found');
        results.notes.push('Math Tutor: tab loaded but no recognizable form');
      }
    }
  } catch (e) {
    console.error('  FAIL:', e.message);
    results.failed.push('Math Tutor: ' + e.message);
  }

  // Print results
  console.log('\n\n=== RESULTS ===');
  results.passed.forEach(a => console.log('  ✅', a));
  results.failed.forEach(a => console.log('  ❌', a));
  results.notes.forEach(a => console.log('  ℹ️', a));

  if (consoleErrors.length > 0) {
    console.log('\nConsole errors:', consoleErrors.length);
    consoleErrors.forEach(e => console.log('  ⚠', e));
  } else {
    console.log('\nNo console errors.');
  }

  await browser.close();

  fs.writeFileSync('tests/test_results2.json', JSON.stringify({
    timestamp: new Date().toISOString(),
    results, consoleErrors,
  }, null, 2));

  if (results.failed.length > 0) process.exit(1);
  process.exit(0);
}

main().catch(e => { console.error(e); process.exit(1); });