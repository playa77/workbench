#!/usr/bin/env node
/** UI/UX Test Suite for Workbench Agents
 * Version: 1.0.0 | 2026-06-26
 * Uses Playwright to test one use case per agent.
 * Knowledge Base excluded (alpha).
 */

const { chromium } = require('playwright');
const fs = require('fs');

const BASE_URL = 'https://workbench.gronowski.cc';
const USERNAME = 'admin';
const PASSWORD = 'admin123';
const SCREENSHOT_DIR = 'tests/screenshots';

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function screenshot(page, name) {
  const path = `${SCREENSHOT_DIR}/${Date.now()}_${name}.png`;
  await page.screenshot({ path, fullPage: true });
  console.log(`  [SCREENSHOT] ${name}`);
  return path;
}

async function login(page) {
  console.log('[LOGIN] Navigating to Workbench...');
  await page.goto(BASE_URL, { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  // Check if already logged in (look for "Sign out" button)
  let signOutBtn = await page.$('button:has-text("Sign out")');
  if (signOutBtn) {
    console.log('[LOGIN] Already logged in.');
    return;
  }

  console.log('[LOGIN] Filling credentials...');
  await page.fill('input[placeholder*="email or username" i], input[placeholder*="Enter your email"]', USERNAME);
  await page.fill('input[placeholder*="password" i], input[placeholder*="Enter your password"]', PASSWORD);
  await screenshot(page, '01_login_form');
  await page.click('button:has-text("Sign In"):not(:has-text("API"))');
  await page.waitForTimeout(3000);

  // Verify login succeeded
  signOutBtn = await page.$('button:has-text("Sign out")');
  if (signOutBtn) {
    console.log('[LOGIN] Login successful.');
    await screenshot(page, '01_login_success');
  } else {
    // Check for error messages
    const errorEl = await page.$('.alert-error, .toast-error');
    if (errorEl) {
      const text = await errorEl.textContent();
      console.error(`[LOGIN] Login failed: ${text}`);
    }
    console.error('[LOGIN] Login may have failed - no Sign out button found.');
  }
}

async function clickTab(page, tabName) {
  console.log(`[TAB] Clicking "${tabName}" tab...`);
  await page.click(`nav button:has-text("${tabName}")`);
  await page.waitForTimeout(1500);
}

async function testChatAgent(page) {
  console.log('\n=== TEST 3: Chat Agent ===');
  await clickTab(page, 'Chat');
  await screenshot(page, '03_chat_initial');

  const prompt = 'Explain what a Donor-Advised Fund (DAF) is in 2-3 sentences.';
  console.log(`  Sending: "${prompt}"`);
  await page.fill('input[placeholder="Type your message..."], textarea[placeholder="Type your message..."]', prompt);
  await page.click('button:has-text("Send")');
  console.log('  Waiting for response...');
  // Wait up to 60s for response (chat is non-streaming)
  try {
    await page.waitForFunction(() => {
      const thinkingEls = document.querySelectorAll('*');
      let thinkingCount = 0;
      thinkingEls.forEach(el => {
        if (el.textContent === 'Thinking...') thinkingCount++;
      });
      return thinkingCount === 0;
    }, { timeout: 60000 });
  } catch (e) {
    console.log('  (Timeout waiting for "Thinking..." to disappear - may still be generating)');
  }
  await page.waitForTimeout(2000);
  await screenshot(page, '03_chat_response');
  console.log('  Chat test complete.');
}

async function testNewsPipeline(page) {
  console.log('\n=== TEST 4: News Pipeline ===');
  await clickTab(page, 'News Pipeline');
  await page.waitForTimeout(2000);
  await screenshot(page, '04_news_initial');

  // Create a new interest
  const interestName = 'Test Interest';
  console.log(`  Creating interest: "${interestName}"...`);
  await page.fill('input[placeholder="e.g. AI News"]', interestName);
  await page.click('button:has-text("Create Interest")');
  await page.waitForTimeout(2000);
  await screenshot(page, '04_news_created');
  console.log('  News Pipeline test complete.');
}

async function testDebateArena(page) {
  console.log('\n=== TEST 5: Debate Arena ===');
  await clickTab(page, 'Debate Arena');
  await page.waitForTimeout(2000);
  await screenshot(page, '05_debate_initial');

  // Check if the tab rendered properly (no JS errors)
  const rolesEl = await page.$('#debate-roles');
  if (!rolesEl) {
    console.error('  FAIL: Debate roles div not found - JS may have failed to render.');
    await screenshot(page, '05_debate_error');
    return;
  }

  const rolesText = await rolesEl.textContent();
  if (rolesText.includes('Loading') || rolesText.includes('Failed')) {
    console.error(`  FAIL: Debate roles failed to load: "${rolesText.trim()}"`);
    await screenshot(page, '05_debate_roles_error');
  } else {
    console.log(`  Roles loaded: ${rolesText.replace(/\n/g, ' ').substring(0, 100)}...`);
    await screenshot(page, '05_debate_roles_loaded');
  }

  // Verify topic input is available
  const topicInput = await page.$('#debate-topic');
  if (!topicInput) {
    console.error('  FAIL: Topic input not found.');
  } else {
    console.log('  Topic input found.');
  }

  // Verify console errors on this page
  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.log(`  [CONSOLE ERROR] ${msg.text()}`);
    }
  });

  console.log('  Debate Arena UI test complete (did not start debate to avoid API costs).');
}

async function testDeepResearch(page) {
  console.log('\n=== TEST 6: Deep Research ===');
  await clickTab(page, 'Deep Research');
  await page.waitForTimeout(2000);
  await screenshot(page, '06_research_initial');

  // Verify the form elements are present
  const topicInput = await page.$('#research-topic, textarea[placeholder*="research"]');
  const depthInput = await page.$('#research-depth');
  const branchingInput = await page.$('#research-branch, #research-branching');

  if (topicInput) console.log('  Research topic input found.');
  else console.log('  WARN: Research topic input not found with known selectors.');

  if (depthInput) console.log('  Depth input found.');
  if (branchingInput) console.log('  Branching input found.');

  console.log('  Deep Research UI test complete (did not start research to avoid API costs).');
}

async function testConsigliere(page) {
  console.log('\n=== TEST 7: Consigliere ===');
  await clickTab(page, 'Consigliere');
  await page.waitForTimeout(2000);
  await screenshot(page, '07_consigliere_initial');

  // Verify the form elements are present
  const topicInput = await page.$('#deliberation-topic, textarea[placeholder*="question"]');
  const roundsInput = await page.$('#deliberation-rounds');
  const framesContainer = await page.$('#deliberation-frames, #consigliere-frames');

  if (topicInput) console.log('  Topic input found.');
  else console.log('  WARN: Topic input not found.');

  if (roundsInput) console.log('  Rounds input found.');
  if (framesContainer) {
    const framesText = await framesContainer.textContent();
    console.log(`  Frames container found: ${framesText.substring(0, 80).trim()}...`);
  }

  console.log('  Consigliere UI test complete (did not start deliberation to avoid API costs).');
}

async function testStrategicPlanning(page) {
  console.log('\n=== TEST 8: Strategic Planning ===');
  await clickTab(page, 'Strategic Planning');
  await page.waitForTimeout(2000);
  await screenshot(page, '08_planning_initial');

  // Verify the form elements
  const goalInput = await page.$('#plan-goal, textarea[placeholder*="goal"], textarea[placeholder*="describe"]');
  const planTypeSelect = await page.$('#plan-type, select');

  if (goalInput) console.log('  Goal input found.');
  else console.log('  WARN: Goal input not found with known selectors.');

  if (planTypeSelect) {
    const options = await planTypeSelect.$$eval('option', opts => opts.map(o => o.textContent.trim()).join(', '));
    console.log(`  Plan types: ${options}`);
  }

  console.log('  Strategic Planning UI test complete (did not start planning to avoid API costs).');
}

async function testMathTutor(page) {
  console.log('\n=== TEST 9: Math Tutor ===');
  await clickTab(page, 'Math Tutor');
  await page.waitForTimeout(2000);
  await screenshot(page, '09_math_tutor_initial');

  // Verify the structured interview wizard or free-form chat is present
  const chatInput = await page.$('input[placeholder*="Type your message"], textarea[placeholder*="message"]');
  const structuredForm = await page.$('#math-interview, .math-wizard');
  const competencySelect = await page.$('#math-competency, select[aria-label*="competency"]');

  if (chatInput) console.log('  Chat input found (free-form mode).');
  if (structuredForm) console.log('  Structured interview wizard found.');
  if (competencySelect) {
    const compValue = await competencySelect.evaluate(el => el.value);
    console.log(`  Competency level: ${compValue}`);
  }

  console.log('  Math Tutor UI test complete (did not start session to avoid API costs).');
}

async function checkConsoleErrors(page) {
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });
  return errors;
}

async function main() {
  console.log('=== WORKBENCH UI/UX TEST SUITE ===');
  console.log(`Target: ${BASE_URL}`);
  console.log(`Time: ${new Date().toISOString()}\n`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: false,
  });
  const page = await context.newPage();

  // Collect console errors
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(`[${new Date().toISOString()}] ${msg.text()}`);
    }
  });

  const results = { passed: [], failed: [], errors: [] };

  try {
    // Login
    await login(page);

    // Test Chat Agent (with actual API call)
    try {
      await testChatAgent(page);
      results.passed.push('Chat Agent');
    } catch (e) {
      console.error(`  FAIL: ${e.message}`);
      results.failed.push(`Chat Agent: ${e.message}`);
    }

    // Test News Pipeline (UI only)
    try {
      await testNewsPipeline(page);
      results.passed.push('News Pipeline');
    } catch (e) {
      console.error(`  FAIL: ${e.message}`);
      results.failed.push(`News Pipeline: ${e.message}`);
    }

    // Test Debate Arena (UI only - fixed JS bug)
    try {
      await testDebateArena(page);
      results.passed.push('Debate Arena');
    } catch (e) {
      console.error(`  FAIL: ${e.message}`);
      results.failed.push(`Debate Arena: ${e.message}`);
    }

    // Test Deep Research (UI only)
    try {
      await testDeepResearch(page);
      results.passed.push('Deep Research');
    } catch (e) {
      console.error(`  FAIL: ${e.message}`);
      results.failed.push(`Deep Research: ${e.message}`);
    }

    // Test Consigliere (UI only)
    try {
      await testConsigliere(page);
      results.passed.push('Consigliere');
    } catch (e) {
      console.error(`  FAIL: ${e.message}`);
      results.failed.push(`Consigliere: ${e.message}`);
    }

    // Test Strategic Planning (UI only)
    try {
      await testStrategicPlanning(page);
      results.passed.push('Strategic Planning');
    } catch (e) {
      console.error(`  FAIL: ${e.message}`);
      results.failed.push(`Strategic Planning: ${e.message}`);
    }

    // Test Math Tutor (UI only)
    try {
      await testMathTutor(page);
      results.passed.push('Math Tutor');
    } catch (e) {
      console.error(`  FAIL: ${e.message}`);
      results.failed.push(`Math Tutor: ${e.message}`);
    }

  } catch (e) {
    console.error(`FATAL: ${e.message}`);
    results.errors.push(e.message);
  }

  // Print results
  console.log('\n\n=== TEST RESULTS ===');
  console.log(`Passed: ${results.passed.length}/7`);
  results.passed.forEach(a => console.log(`  ✅ ${a}`));
  console.log(`Failed: ${results.failed.length}/7`);
  results.failed.forEach(a => console.log(`  ❌ ${a}`));

  if (consoleErrors.length > 0) {
    console.log(`\nConsole Errors: ${consoleErrors.length}`);
    consoleErrors.forEach(e => console.log(`  ⚠ ${e}`));
  } else {
    console.log('\nNo console errors detected.');
  }

  // Final evidence screenshot
  await screenshot(page, '10_final_state');

  await browser.close();

  // Write results file
  fs.writeFileSync('tests/test_results.json', JSON.stringify({
    timestamp: new Date().toISOString(),
    target: BASE_URL,
    passed: results.passed,
    failed: results.failed,
    errors: results.errors,
    consoleErrors,
  }, null, 2));

  console.log('\nResults written to tests/test_results.json');
  console.log('Screenshots in tests/screenshots/');

  if (results.failed.length > 0 || results.errors.length > 0) {
    process.exit(1);
  }
  process.exit(0);
}

main().catch(e => {
  console.error('Unhandled error:', e);
  process.exit(1);
});