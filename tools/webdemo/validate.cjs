// Development-only browser acceptance; the shipped application needs only Go.
const {chromium}=require('playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..');
const out=path.join(root,'go/reports/v2.2.0');
const base=process.env.PSDANA_URL||'http://127.0.0.1:8080';
const captures={qam:path.join(root,'data/qam64_20MSymPS_160MSPS_RRC0p25.csv'),sine:path.join(root,'data/sine_+40MHz_160MSPS.csv')};
const report={status:'RUNNING',viewports:[],checks:[],errors:[]};
const check=(name)=>{report.checks.push(name);console.log('PASS',name);};
(async()=>{
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({headless:true,channel:process.env.PSDANA_BROWSER||'chrome'});
  const context=await browser.newContext({viewport:{width:540,height:960},deviceScaleFactor:1});
  const page=await context.newPage();
  let requests=0;
  page.on('pageerror',e=>report.errors.push(e.message));
  page.on('request',r=>{if(r.url().endsWith('/api/analyze'))requests++;});
  const status=()=>page.locator('#status').innerText();
  const waitState=async value=>page.waitForFunction(v=>document.getElementById('status').textContent.startsWith(v),value,{timeout:120000});
  const edit=async(key,value,cancel=false)=>{
    await page.locator(`[data-parameter="${key}"]`).click();
    const input=page.locator('.inline-editor');await input.fill(value);await input.press(cancel?'Escape':'Enter');
  };
  const run=async()=>{
    const pending=page.waitForResponse(r=>r.url().endsWith('/api/analyze'));
    await page.locator('#analyze').click();
    const response=await pending;const json=await response.json();
    await waitState(json.status);return json;
  };
  try {
    await page.goto(base);await page.evaluate(()=>document.fonts.ready);
    assert.equal(await status(),'NO FILE');assert(await page.locator('#analyze').isDisabled());
    const chooserPromise=page.waitForEvent('filechooser');await page.locator('#choose-file').click();await chooserPromise;
    assert.equal(await page.evaluate(()=>echarts.version),'6.0.0');check('Initial empty state / local ECharts 6');
    // A browser DataTransfer dispatches a real File at the global body drop target.
    const contents=fs.readFileSync(captures.qam,'utf8');
    await page.evaluate(({contents})=>{
      const transfer=new DataTransfer();transfer.items.add(new File([contents],'qam64_20MSymPS_160MSPS_RRC0p25.csv',{type:'text/csv'}));
      document.body.dispatchEvent(new DragEvent('dragenter',{bubbles:true,dataTransfer:transfer}));
      window.__dropForTest=transfer;
    },{contents});
    assert(await page.locator('#drop-overlay').isVisible());
    await page.evaluate(()=>document.body.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:window.__dropForTest})));
    assert.equal(await status(),'FILE READY');assert.equal(requests,0);assert(await page.locator('#drop-overlay').isHidden());check('Global drag overlay / selection only, no automatic upload');
    const qam=await run();assert.equal(qam.status,'COMPLETE');
    assert.equal(await page.locator('#primary-value').innerText(),qam.power_metrics.average_power_dbfs.toFixed(2).replace('-','−'));
    fs.writeFileSync(path.join(out,'qam-http.json'),JSON.stringify(qam));
    check('CSV → HTTP → Go → JSON → PSD metrics');
    await page.locator('#tab-qam').click();
    assert.equal(await page.locator('#primary-value').innerText(),qam.qam_metrics.evm_pct_rms.toFixed(2));
    assert((await page.locator('#auxiliary').innerText()).includes(qam.qam_metrics.phase_error_pct_rms.toFixed(2)+' %rms'));
    assert.equal(requests,1);check('QAM percent metrics / tab preserves results without requests');
    for(const [width,height] of [[540,960],[1080,1920],[1920,1080],[2560,1440],[3840,2160],[390,844],[2560,3000]]) {
      await page.setViewportSize({width,height});
      await page.waitForFunction(()=>Math.abs(document.getElementById('instrument').getBoundingClientRect().height-Math.min(innerWidth/540,innerHeight/960,2.25)*960)<.1);
      for(const mode of ['psd','qam']) {
        await page.locator('#tab-'+mode).click();
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        const layout=await page.evaluate(()=>{
          const app=document.getElementById('instrument'),chart=document.getElementById('chart'),rect=app.getBoundingClientRect();
          const c=echarts.getInstanceByDom(chart),o=c.getOption();
          return {x:rect.x,y:rect.y,width:rect.width,height:rect.height,scrollWidth:document.documentElement.scrollWidth,viewportWidth:innerWidth,
            background:getComputedStyle(document.documentElement).backgroundColor,appBackground:getComputedStyle(app).backgroundColor,border:getComputedStyle(app).borderWidth,shadow:getComputedStyle(app).boxShadow,
            grid:o.grid[0],canvas:!!chart.querySelector('canvas'),series:o.series.map(s=>({type:s.type,count:s.data.length})),
            legend:[...document.querySelectorAll('#legend img')].map(i=>({width:i.getBoundingClientRect().width,height:i.getBoundingClientRect().height,loaded:i.complete&&i.naturalWidth>0}))};
        });
        const scale=Math.min(width/540,height/960,2.25);
        assert(Math.abs(layout.width-540*scale)<.1);assert(Math.abs(layout.height-960*scale)<.1);
        assert(Math.abs(layout.x-(width-layout.width)/2)<.1);assert(Math.abs(layout.y-(height-layout.height)/2)<.1);
        assert(layout.height<=2160.1);assert(layout.scrollWidth<=width);assert.equal(layout.shadow,'none');assert.equal(layout.border,'0px');assert.equal(layout.background,'rgb(245, 243, 238)');assert(layout.canvas);
        if(mode==='qam'){assert.equal(layout.grid.width,layout.grid.height);assert(layout.legend.every(i=>i.loaded));assert(Math.abs(layout.legend[0].width-10*scale)<.1);}
        const name=`${mode}-${width}x${height}.png`;await page.screenshot({path:path.join(out,name)});
        report.viewports.push({width,height,mode,screenshot:name,...layout});
      }
    }
    check('14 responsive screenshots / 9:16 / centered / max 2160 CSS px / QAM equal axes');
    for(const viewport of [{width:390,height:844},{width:1080,height:1920}]){
      await page.setViewportSize(viewport);await page.locator('#tab-qam').click();
      await edit('rrc_beta','0.5');await edit('rrc_beta','0.25');
      await page.locator('[data-parameter="rrc_beta"]').hover();
      assert.equal(await page.locator('[data-parameter="rrc_beta"]').evaluate(e=>getComputedStyle(e).color),'rgb(228, 81, 55)');
    }
    // Browser device pixels do not change the 2160 CSS-pixel layout cap.
    const retina=await browser.newContext({viewport:{width:540,height:960},deviceScaleFactor:2});
    const retinaPage=await retina.newPage();await retinaPage.goto(base);
    const retinaSize=await retinaPage.locator('#instrument').boundingBox();assert.equal(retinaSize.height,960);assert.equal(retinaSize.width,540);await retina.close();
    check('Scaled click/edit/hover coordinates at mobile and 2x; DPR independent layout');
    await page.setViewportSize({width:540,height:960});
    await edit('sample_rate_hz','320',true);assert.equal(await page.locator('[data-parameter="sample_rate_hz"]').innerText(),'160');
    await edit('sample_rate_hz','320');assert((await status()).includes('STALE'));await page.locator('#tab-psd').click();
    assert.equal(await page.locator('[data-parameter="sample_rate_hz"]').innerText(),'320');assert.equal(requests,1);
    await edit('sample_rate_hz','160');
    const idle=await page.locator('[data-parameter="sample_rate_hz"]').evaluate(e=>({border:getComputedStyle(e).borderWidth,background:getComputedStyle(e).backgroundColor}));
    assert.equal(idle.border,'0px');assert.equal(idle.background,'rgba(0, 0, 0, 0)');check('Enter commit / Escape cancel / shared sample rate / stale / borderless idle');
    await page.locator('#tab-psd').focus();await page.keyboard.press('ArrowRight');assert.equal(await page.locator('#tab-qam').getAttribute('aria-selected'),'true');
    await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.dataset.parameter),'symbol_rate_hz');
    assert.equal(await page.evaluate(()=>getComputedStyle(document.activeElement).outlineStyle),'solid');
    await page.locator('#tab-psd').click();check('Keyboard tab navigation and visible parameter focus');
    await edit('power_band_left_hz','90');assert(await page.locator('#analyze').isDisabled());
    await edit('power_band_left_hz','-20');await edit('sample_rate_hz','30');assert(await page.locator('#analyze').isDisabled());
    await edit('sample_rate_hz','160');await page.locator('#tab-qam').click();
    await edit('symbol_rate_hz','21');assert(await page.locator('#analyze').isDisabled());await edit('symbol_rate_hz','20');
    await edit('rrc_beta','1.1');assert(await page.locator('#analyze').isDisabled());await edit('rrc_beta','0.25');check('Band, changed Nyquist, SPS and RRC validation');
    await page.locator('#file-input').setInputFiles(captures.sine);assert.equal(await page.locator('#primary-value').innerText(),'—');
    await page.locator('#tab-psd').click();await edit('power_band_left_hz','39');await edit('power_band_right_hz','41');
    const sine=await run();assert.equal(sine.status,'PARTIAL');assert.equal(sine.power_metrics.peak_frequency_hz,40e6);
    fs.writeFileSync(path.join(out,'sine-http.json'),JSON.stringify(sine));
    await page.screenshot({path:path.join(out,'sine-band-39-41.png')});
    await edit('power_band_left_hz','40');await edit('power_band_right_hz','40');
    assert(!(await page.locator('#analyze').isDisabled()));
    const point=await run();assert.equal(point.status,'PARTIAL');assert.equal(point.power_metrics.is_point,true);
    assert.equal(point.power_metrics.contributing_bins,1);assert.equal(point.power_metrics.peak_frequency_hz,40e6);
    assert.equal(point.power_metrics.average_power_dbfs,point.power_metrics.peak_power_dbfs);
    assert.equal(await page.locator('#primary-value').innerText(),point.power_metrics.average_power_dbfs.toFixed(2).replace('-','−'));
    fs.writeFileSync(path.join(out,'sine-point-http.json'),JSON.stringify(point));
    await page.screenshot({path:path.join(out,'sine-point-40MHz.png')});
    await edit('power_band_left_hz','41');assert(await page.locator('#analyze').isDisabled());await edit('power_band_left_hz','40');
    check('Equal power bounds enable ANALYZE / real 40 MHz single-bin RBW measurement / reversed bounds rejected');
    await page.locator('#tab-qam').click();assert.equal(await page.locator('#primary-value').innerText(),'—');
    assert.equal(await page.evaluate(()=>echarts.getInstanceByDom(document.getElementById('chart')).getOption().series[0].data.length),0);check('File replacement clears results / sine 39–41 MHz / PARTIAL clears constellation');
    await page.locator('#file-input').setInputFiles({name:'invalid.csv',mimeType:'text/csv',buffer:Buffer.from('i,q\n0.25,-0.5\n')});
    const bad=await run();assert.equal(bad.status,'ERROR');assert(!(await page.locator('#analyze').isDisabled()));check('Real parse error / retry enabled');
    const longName='capture_'.repeat(30)+'.csv';
    await page.locator('#file-input').setInputFiles({name:longName,mimeType:'text/csv',buffer:Buffer.from(contents)});
    assert.equal(await page.locator('#choose-file').getAttribute('title'),longName);
    assert(await page.locator('#filename').evaluate(e=>e.scrollWidth>e.clientWidth));check('Long basename truncation and full hover title');
    await page.locator('#tab-psd').click();await edit('power_band_left_hz','-20');await edit('power_band_right_hz','20');
    const retry=await run();assert.equal(retry.status,'COMPLETE');check('Retry with a real valid CSV succeeds');
    // Delay delivery of a REAL completed response, replace file, then release it.
    let release,ready;const gate=new Promise(r=>release=r),arrived=new Promise(r=>ready=r);
    await page.route('**/api/analyze',async route=>{const real=await route.fetch();ready();await gate;await route.fulfill({response:real}).catch(()=>{});});
    await page.locator('#analyze').click();assert(await page.locator('#analyze').isDisabled());await arrived;
    await page.locator('#file-input').setInputFiles(captures.sine);release();await page.unrouteAll({behavior:'wait'});
    await page.waitForTimeout(150);assert.equal(await status(),'FILE READY');assert.equal(await page.locator('#primary-value').innerText(),'—');check('Duplicate submit disabled / late real response cannot overwrite replacement file');
    // Transport failure, without synthetic successful data.
    await page.route('**/api/analyze',route=>route.abort('failed'));
    await page.locator('#analyze').click();await waitState('ERROR');assert(!(await page.locator('#analyze').isDisabled()));await page.unrouteAll();check('Network failure permits retry');
    assert.deepEqual(report.errors,[]);report.status='PASS';
  } catch(error){report.status='FAIL';report.failure=error.stack;throw error;}
  finally {fs.writeFileSync(path.join(out,'browser-validation.json'),JSON.stringify(report,null,2));await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
