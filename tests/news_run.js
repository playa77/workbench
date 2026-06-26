#!/usr/bin/env node
const { chromium } = require('playwright');
(async () => {
  console.log('[1] Launch and navigate...');
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } });
  
  await page.goto('https://workbench.gronowski.cc', { waitUntil: 'load', timeout: 20000 });
  await page.waitForTimeout(2000);

  // Login
  const signOut = await page.$('button:has-text("Sign out")');
  if (!signOut) {
    console.log('[2] Logging in...');
    await page.fill('input[placeholder="Enter your email or username"]', 'admin');
    await page.fill('input[placeholder="Enter your password"]', 'admin123');
    await page.click('button:has-text("Sign In"):not(:has-text("API"))');
    await page.waitForSelector('button:has-text("Sign out")', { timeout: 10000 });
    console.log('   Logged in.');
  } else {
    console.log('[2] Already logged in.');
  }

  // Navigate to News Pipeline
  console.log('[3] Navigating to News Pipeline...');
  await page.click('nav button:has-text("News Pipeline")');
  await page.waitForTimeout(2000);

  // Find and click Run Now for AI News
  console.log('[4] Clicking Run Now on AI News...');
  // The "AI News" interest's Run Now button calls window.newsTriggerRun(1, this)
  // We can call it directly from the page context
  const result = await page.evaluate(async () => {
    try {
      // Get API key from the app
      const key = typeof API !== 'undefined' && API.getApiKey ? API.getApiKey() : '';
      const headers = { 'Content-Type': 'application/json' };
      if (key) headers['Authorization'] = 'Bearer ' + key;
      
      const resp = await fetch('/api/v1/agents/news/interests/1/run', { 
        method: 'POST', 
        headers,
        credentials: 'include'  // Send session cookie
      });
      const data = await resp.json();
      return { ok: resp.ok, status: resp.status, data };
    } catch (e) {
      return { error: e.message };
    }
  });
  console.log('   Result:', JSON.stringify(result));

  if (result.ok && result.data && result.data.run_id) {
    console.log(`[5] Run #${result.data.run_id} started! Polling for completion...`);
    
    // Poll for completion
    for (let i = 0; i < 60; i++) {
      await page.waitForTimeout(5000);
      const status = await page.evaluate(async (runId) => {
        try {
          const resp = await fetch(`/api/v1/agents/news/interests/1/runs`);
          const data = await resp.json();
          const run = (data.runs || []).find(r => r.id === runId);
          return run ? { status: run.status, stage: run.current_stage || '' } : null;
        } catch (e) { return null; }
      }, result.data.run_id);
      
      if (status) {
        console.log(`   Poll ${i+1}: status=${status.status}, stage=${status.stage}`);
        if (status.status === 'completed') {
          console.log('   ✅ Pipeline completed!');
          break;
        } else if (status.status === 'failed') {
          console.log('   ❌ Pipeline failed!');
          break;
        }
      }
    }
  }

  // Check the runs in the UI
  console.log('[6] Clicking Load Runs...');
  await page.click('button:has-text("Load Runs")');
  await page.waitForTimeout(2000);
  const runsText = await page.$eval('[id^="news-runs-"]', el => el.textContent).catch(() => 'NOT FOUND');
  console.log('   Runs UI:', runsText.substring(0, 200));

  await browser.close();
  console.log('\nDone.');
})();