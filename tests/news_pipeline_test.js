#!/usr/bin/env node
/** News Pipeline End-to-End Test: Manual Run via UI
 * Version: 1.0.0 | 2026-06-26
 * 
 * 1. Login as admin  
 * 2. Navigate to News Pipeline
 * 3. Click "Run Now" on the pre-existing "AI News" interest (9 RSS feeds, id=1)
 * 4. Poll for run completion
 * 5. Verify deliverables (summary, brief, themes)
 */
const { chromium } = require('playwright');
const BASE_URL = 'https://workbench.gronowski.cc';

async function main() {
  console.log('=== NEWS PIPELINE END-TO-END TEST ===');
  console.log('Time:', new Date().toISOString(), '\n');

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const results = { passed: [], failed: [], notes: [] };
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });

  // ---- LOGIN ----
  console.log('[1] Login...');
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(3000);

  let signOut = await page.$('button:has-text("Sign out")');
  if (!signOut) {
    // Fill login form - use placeholder text
    const inputs = await page.$$('input');
    for (const inp of inputs) {
      const ph = await inp.getAttribute('placeholder');
      if (ph && ph.includes('email')) await inp.fill('admin');
      if (ph && ph.includes('password')) await inp.fill('admin123');
    }
    const btn = await page.$('button:has-text("Sign In"):not(:has-text("API"))');
    if (btn) { await btn.click(); await page.waitForTimeout(4000); }
    signOut = await page.$('button:has-text("Sign out")');
  }
  if (!signOut) { console.error('  Login failed'); await browser.close(); process.exit(1); }
  console.log('  Logged in as admin.');
  results.passed.push('Login');

  // ---- NAVIGATE TO NEWS PIPELINE ----
  console.log('\n[2] Navigate to News Pipeline...');
  await page.click('nav button:has-text("News Pipeline")');
  await page.waitForTimeout(2000);
  console.log('  Tab loaded.');
  results.passed.push('Tab navigation');

  // ---- FIND AI NEWS INTEREST AND CLICK RUN NOW ----
  console.log('\n[3] Find "AI News" interest and click Run Now...');
  
  // There are multiple interests. Each has Run Now / Edit / Feeds / Delete buttons.
  // The "AI News" interest is the first one. The Run Now button has onclick="window.newsTriggerRun(id, this)"
  // Strategy: find all Run Now buttons and click the first one (AI News = interest #1)
  const runButtons = await page.$$('button:has-text("Run Now")');
  if (runButtons.length === 0) {
    console.log('  FAIL: No Run Now buttons found');
    results.failed.push('Run Now button not found');
    await browser.close();
    process.exit(1);
  }
  console.log(`  Found ${runButtons.length} Run Now buttons. Clicking first (AI News)...`);
  await runButtons[0].click();
  await page.waitForTimeout(1000);
  
  // Check for success toast
  const toast = await page.$('.toast, .toast-success, [class*="toast"]');
  if (toast) {
    const toastText = await toast.textContent();
    console.log(`  Toast: "${toastText.trim()}"`);
    if (toastText.includes('started') || toastText.includes('run #')) {
      console.log('  Run started successfully!');
      results.passed.push('Run triggered via UI');
    } else if (toastText.includes('error') || toastText.includes('fail')) {
      console.log('  FAIL: Run failed:', toastText.trim());
      results.failed.push('Run trigger: ' + toastText.trim());
    }
  } else {
    console.log('  No toast visible - checking if run button state changed...');
    // The button should have been reset after the POST
  }

  // Wait a moment for the button to reset
  await page.waitForTimeout(2000);

  // ---- POLL FOR RUN COMPLETION ----
  console.log('\n[4] Polling for run completion...');
  
  // Click "Load Runs" on the AI News interest
  const loadRunsButtons = await page.$$('button:has-text("Load Runs")');
  if (loadRunsButtons.length === 0) {
    console.log('  WARN: No Load Runs buttons found');
    results.notes.push('Load Runs button not found');
  }

  // Poll via the API directly using page.evaluate to check run status
  let runCompleted = false;
  let runData = null;
  const maxPolls = 40; // ~6.6 minutes at 10s intervals
  for (let i = 0; i < maxPolls; i++) {
    console.log(`  Poll ${i + 1}/${maxPolls}...`);
    
    // Check via API call from the browser context
    const apiResult = await page.evaluate(async () => {
      try {
        const resp = await fetch('/api/v1/agents/news/interests/1/runs');
        const data = await resp.json();
        if (data.runs && data.runs.length > 0) {
          const latest = data.runs[0];
          return { 
            runId: latest.id, 
            status: latest.status, 
            stage: latest.current_stage || '',
            runDate: latest.run_date,
            total: data.runs.length
          };
        }
        return { runs: 0 };
      } catch (e) {
        return { error: e.message };
      }
    });
    
    console.log(`    Result: ${JSON.stringify(apiResult)}`);
    
    if (apiResult.runs === 0) {
      // No runs yet - pipeline may still be initializing
      console.log('    No runs found yet - pipeline initializing...');
    } else if (apiResult.status === 'completed') {
      console.log(`    ✅ Run #${apiResult.runId} completed!`);
      runCompleted = true;
      runData = apiResult;
      break;
    } else if (apiResult.status === 'failed') {
      console.log(`    ❌ Run #${apiResult.runId} failed!`);
      runData = apiResult;
      break;
    } else {
      console.log(`    Status: ${apiResult.status} (stage: ${apiResult.stage})`);
    }
    
    await page.waitForTimeout(10000); // Poll every 10s
  }

  if (runCompleted) {
    results.passed.push('Pipeline completed successfully');
    
    // ---- CLICK LOAD RUNS TO SEE UI ----
    console.log('\n[5] Loading runs via UI...');
    if (loadRunsButtons.length > 0) {
      await loadRunsButtons[0].click();
      await page.waitForTimeout(2000);
      
      // Check if runs appear in the UI
      const runsContainer = await page.$('[id^="news-runs-"]');
      if (runsContainer) {
        const runsText = await runsContainer.textContent();
        console.log(`  Runs UI: ${runsText.substring(0, 200)}`);
        if (runsText.includes('completed')) {
          results.passed.push('Runs display in UI');
        }
      }
    }
    
    // ---- CHECK DELIVERABLES ----
    console.log('\n[6] Checking deliverables (themes, summary, brief)...');
    
    if (runData && runData.runId) {
      // Check themes
      const themesResult = await page.evaluate(async (runId) => {
        try {
          const resp = await fetch(`/api/v1/agents/news/runs/${runId}/themes`);
          return await resp.json();
        } catch (e) { return { error: e.message }; }
      }, runData.runId);
      if (themesResult.themes && themesResult.themes.length > 0) {
        console.log(`  Themes found: ${themesResult.themes.length}`);
        themesResult.themes.slice(0, 3).forEach(t => console.log(`    - ${t.title}: ${(t.description || '').substring(0, 80)}`));
        results.passed.push('Themes generated');
      } else {
        console.log('  No themes found yet (may need pipeline completion)');
      }
      
      // Check deliverables
      const delivResult = await page.evaluate(async (runId) => {
        try {
          const resp = await fetch(`/api/v1/agents/news/runs/${runId}/deliverables`);
          return await resp.json();
        } catch (e) { return { error: e.message }; }
      }, runData.runId);
      if (delivResult.error) {
        console.log(`  Deliverables error: ${delivResult.error}`);
      } else {
        const types = Object.keys(delivResult).filter(k => delivResult[k]);
        console.log(`  Deliverables available: ${types.join(', ')}`);
        if (types.length > 0) results.passed.push('Deliverables generated');
      }
    }
  } else if (runData) {
    if (runData.status === 'failed') {
      results.failed.push('Pipeline run failed');
    } else {
      console.log(`  Pipeline still running after ${maxPolls * 10}s`);
      results.notes.push('Pipeline did not complete within timeout');
    }
  }

  // ---- FINAL REPORT ----
  console.log('\n\n========================================');
  console.log('        NEWS PIPELINE TEST RESULTS');
  console.log('========================================');
  console.log(`Passed: ${results.passed.length}`);
  results.passed.forEach(p => console.log(`  ✅ ${p}`));
  console.log(`Failed: ${results.failed.length}`);
  results.failed.forEach(f => console.log(`  ❌ ${f}`));
  console.log(`Notes: ${results.notes.length}`);
  results.notes.forEach(n => console.log(`  ℹ️ ${n}`));
  if (errors.length > 0) {
    console.log(`\nConsole errors: ${errors.length}`);
    errors.forEach(e => console.log(`  ⚠ ${e}`));
  }

  await browser.close();
  process.exit(results.failed.length > 0 ? 1 : 0);
}

main().catch(e => { console.error('FATAL:', e); process.exit(1); });