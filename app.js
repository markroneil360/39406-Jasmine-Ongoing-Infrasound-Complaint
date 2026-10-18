'use strict';
const $=id=>document.getElementById(id);
const et=value=>value?new Date(value).toLocaleString('en-US',{timeZone:'America/New_York',dateStyle:'medium',timeStyle:'medium'}):'Not available';
const num=n=>Number(n).toLocaleString('en-US',{maximumFractionDigits:2});
const duration=seconds=>{const s=Math.round(seconds),h=Math.floor(s/3600),m=Math.floor(s%3600/60),r=s%60;return `${h}h ${m}m${h<1?' '+r+'s':''}`};
const text=(id,value)=>$(id).textContent=value;
const row=(target,values)=>{const tr=document.createElement('tr');values.forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.append(td)});$(target).append(tr)};
let summary,eventdoc,observations,allEvents=false;
function renderOverview(){
  const w=summary.windows[$('window').value],h=w.channels.HDF,e=w.channels.EHZ;
  text('window-label',`${et(w.start)} to ${et(w.end)} Eastern. Rolling windows are anchored to the analysis update, not to live data.`);
  for(const [c,v] of [['hdf',h],['ehz',e]]){
    text(c+'-time',duration(v.documented_seconds));text(c+'-minutes',num(v.classified_minutes));
    text(c+'-quality',`${num(v.partial_minutes)} partially observed minute slots; ${num(v.flatline_minutes)} flatline minutes. ${duration(v.missing_seconds)} unavailable in this calendar span.`);
  }
  text('hdf-band',h.classified_minutes?num(h.band_counts['4-8']):'Not classified');
  text('hdf-share',h.band_share_pct['4-8']===null?'Unknown':num(h.band_share_pct['4-8'])+'%');
  text('event-count',h.classified_minutes?num(w.narrow.events_ge_10):'Not classifiable');
  text('narrow-run',w.narrow.longest?`Longest 4–8 Hz run: ${duration(w.narrow.longest.minutes*60)}. Minute peaks ${w.narrow.longest.peak_min_hz}–${w.narrow.longest.peak_max_hz} Hz.`:'No complete-minute 4–8 Hz run measured in this window.');
  text('wide-run',w.wide.longest?duration(w.wide.longest.minutes*60):'Not measured');
  $('band-bars').replaceChildren();
  for(const band of ['1-4','4-8','8-16','16-20']){
    const value=h.band_share_pct[band],card=document.createElement('div');card.className='band';
    const name=document.createElement('h3');name.textContent=band.replace('-','–')+' Hz';
    const count=document.createElement('strong');count.textContent=value===null?'Unknown':num(value)+'%';
    const detail=document.createElement('p');detail.className='muted';detail.textContent=value===null?'No classified minutes':num(h.band_counts[band])+' classified minutes';
    const bar=document.createElement('div');bar.className='bar';const fill=document.createElement('span');fill.style.width=(value??0)+'%';bar.append(fill);
    card.append(name,count,detail,bar);$('band-bars').append(card);
  }
}
function renderEvents(){
  const band=$('event-band').value,min=Number($('event-duration').value);
  const entries=(eventdoc[band]||eventdoc.bands[band]).filter(r=>r.minutes>=min).sort((a,b)=>b.minutes-a.minutes);
  $('event-rows').replaceChildren();
  const visible=allEvents?entries:entries.slice(0,30);
  visible.forEach(r=>row('event-rows',[et(r.start_utc),et(r.end_exclusive_utc),`${duration(r.minutes*60)} (${r.minutes} min)`,`${r.peak_min_hz}–${r.peak_max_hz} Hz`]));
  if(!entries.length)row('event-rows',['No qualifying runs in the documented archive.','—','—','—']);
  text('event-summary',`${entries.length} qualifying runs · ${num(entries.reduce((a,r)=>a+r.minutes,0))} complete minutes in these runs · sorted longest first. This register always covers the entire archive.`);
  $('more-events').hidden=allEvents||entries.length<=30;
}
const ns='http://www.w3.org/2000/svg';
function svgNode(name,attributes={},content){
  const node=document.createElementNS(ns,name);
  for(const [k,v] of Object.entries(attributes))node.setAttribute(k,String(v));
  if(content!==undefined)node.textContent=content;return node;
}
function chartBase(id,label){
  const svg=svgNode('svg',{viewBox:'0 0 1000 260',role:'img','aria-label':label});
  svg.append(svgNode('title',{},label));$(id).replaceChildren(svg);return svg;
}
function histogram(){
  const values=summary.peak_frequency_counts,svg=chartBase('frequency-chart','Count of classified HDF minutes by 1–20 Hz peak frequency, entire archive');
  const max=Math.max(1,...Object.values(values));
  for(const frac of [0,.5,1]){
    const y=218-frac*180;svg.append(svgNode('line',{x1:65,y1:y,x2:980,y2:y,stroke:'#2a3b33'}));
    svg.append(svgNode('text',{x:55,y:y+5,'text-anchor':'end'},String(Math.round(max*frac))));
  }
  for(const [hz,count] of Object.entries(values)){
    const x=65+(Number(hz)-1)/19*910,h=count/max*180;
    const rect=svgNode('rect',{x,y:218-h,width:5,height:h,fill:'#55e49c'});
    rect.append(svgNode('title',{},`${hz} Hz: ${count} minutes`));svg.append(rect);
  }
  for(const hz of [1,4,8,12,16,20])svg.append(svgNode('text',{x:65+(hz-1)/19*910,y:245,'text-anchor':'middle'},hz+' Hz'));
}
function amplitude(){
  const svg=chartBase('amplitude-chart','Hourly median HDF raw-count RMS, logarithmic scale. Missing hours are gaps.');
  const hours=summary.hours,values=hours.map(h=>h.channels.HDF.rms_median_counts).filter(v=>v!==null&&v>0);
  if(!values.length){svg.append(svgNode('text',{x:65,y:100},'No complete-minute amplitude observations'));return}
  const lo=Math.floor(Math.log10(Math.min(...values))),hi=Math.max(lo+1,Math.ceil(Math.log10(Math.max(...values))));
  for(let n=lo;n<=hi;n++){
    const y=218-(n-lo)/(hi-lo)*180;svg.append(svgNode('line',{x1:65,y1:y,x2:980,y2:y,stroke:'#2a3b33'}));
    svg.append(svgNode('text',{x:55,y:y+5,'text-anchor':'end'},num(10**n)));
  }
  let path='',active=false;
  hours.forEach((h,i)=>{
    const v=h.channels.HDF.rms_median_counts;
    if(v===null||v<=0){active=false;return}
    const x=65+i/Math.max(1,hours.length-1)*910,y=218-(Math.log10(v)-lo)/(hi-lo)*180;
    path+=(active?'L':'M')+`${x.toFixed(2)},${y.toFixed(2)} `;active=true;
    const point=svgNode('circle',{cx:x,cy:y,r:2,fill:'#55e49c'});point.append(svgNode('title',{},`${et(h.start)} Eastern: ${num(v)} raw counts; ${h.channels.HDF.complete_minutes}/60 full minutes`));svg.append(point);
  });
  svg.append(svgNode('path',{d:path,fill:'none',stroke:'#55e49c','stroke-width':1.6}));
  for(const i of [0,Math.floor((hours.length-1)/2),hours.length-1]){
    const date=new Date(hours[i].start).toLocaleDateString('en-US',{timeZone:'America/New_York',month:'short',day:'numeric'});
    svg.append(svgNode('text',{x:65+i/Math.max(1,hours.length-1)*910,y:245,'text-anchor':i===0?'start':i===hours.length-1?'end':'middle'},date+' ET'));
  }
}
function parseCSV(value){
  const lines=value.trim().split(/\r?\n/),headers=lines.shift().split(',');
  return lines.filter(Boolean).map(line=>Object.fromEntries(line.split(',').map((v,i)=>[headers[i],v])));
}
async function get(name,asText=false){
  const response=await fetch('data/'+name,{cache:'no-store'});if(!response.ok)throw Error(`${name}: HTTP ${response.status}`);
  return asText?response.text():response.json();
}
async function load(){
  try{
    const [status,s,e,sourceDoc,audit,reference,csv]=await Promise.all([get('status.json'),get('summary.json'),get('events.json'),get('sources.json'),get('ingestion-audit.json'),get('reference-audit.json'),get('observations.csv',true)]);
    if([status,s,e,sourceDoc,audit,reference].some(d=>d.station!=='AM.R19BB.00'))throw Error('Station identity mismatch');
    if(status.method!==s.method||s.method!=='detroit-welch-8s-50pct-mean-band-v2')throw Error('Analysis method mismatch');
    summary=s;eventdoc=e;observations=parseCSV(csv);
    text('state',status.state);text('status-note',status.note);
    if(Date.now()-Date.parse(status.generated_utc)>26*3600000)text('state','Archive available · update is stale');
    text('updated',et(status.generated_utc));
    text('latest',`Latest documented HDF sample: ${et(status.latest_documented_samples.HDF)} Eastern. EHZ: ${et(status.latest_documented_samples.EHZ)} Eastern.`);
    (status.channels||[]).forEach(c=>row('attempts',[c.channel,c.error||`${c.complete_minutes} classified complete minutes returned`,et(c.latest_sample_utc)]));
    for(const day of s.days){
      const h=day.channels.HDF,e=day.channels.EHZ;
      row('day-rows',[day.start.slice(0,10),duration(h.documented_seconds),num(h.classified_minutes),h.classified_minutes?num(h.band_counts['4-8']):'Not classifiable',duration(e.documented_seconds),num(h.sample_coverage_pct)+'%']);
    }
    observations.filter(r=>r.quality!=='complete').slice(-16).reverse().forEach(r=>row('partial-rows',[`${r.channel} · ${et(r.minute_utc)}`,num(Number(r.valid_samples)/100)+' s',r.fragment_seconds?num(r.fragment_seconds)+' s':'Not available',r.fragment_band?`${r.fragment_band} Hz / ${r.fragment_peak_hz} Hz`:'No eligible fragment']));
    const gaps=audit.channels.flatMap(c=>(c.unavailable_intervals||[]).map(g=>({channel:c.channel,...g}))).sort((a,b)=>b.seconds-a.seconds);
    gaps.slice(0,30).forEach(g=>row('gap-rows',[g.channel,et(g.start_utc),et(g.end_exclusive_utc),g.seconds<60?num(g.seconds)+' s':duration(g.seconds)]));
    if(gaps.length>30)row('gap-rows',[`Showing 30 longest of ${gaps.length}; full list in the direct-import audit.`,'','','']);
    const sources=sourceDoc.sources.filter(r=>r.source_kind==='direct-device-upload').sort((a,b)=>a.name.localeCompare(b.name));
    text('source-count',`${sources.length} direct-device files · SHA-256 receipts retained`);
    sources.forEach(r=>row('source-rows',[r.name,duration(r.decoded_samples/100),et(r.last_sample_utc),r.decode_warnings.length?`${r.decode_warnings.length} decoder warnings; readable portions retained`:'Decoded without warnings']));
    const warningFiles=sources.filter(r=>r.decode_warnings.length).length;
    const conflicts=audit.channels.reduce((n,c)=>n+c.conflict_samples,0);
    text('quality-note',`${warningFiles} files contain decoder warnings; ${conflicts} conflicting sample positions were excluded. The affected time is not scored as quiet. Original bytes were preserved, and source hashes plus warnings are downloadable.`);
    text('reference-result',`Waveform cross-check: ${num(reference.matching_band_classifications)} of ${num(reference.tested_complete_hdf_minutes)} HDF minute classifications matched the pinned Detroit functions. This audit is tied to the uploaded dataset; it is not a claim of independent verification of later feed additions.`);
    renderOverview();renderEvents();histogram();amplitude();
  }catch(error){
    text('state','Archive verification unavailable');text('status-note',`Could not load consistent dashboard evidence (${error.message}). Do not interpret empty displays as zero measurements.`);
  }
}
$('window').addEventListener('change',()=>{if(summary)renderOverview()});
for(const id of ['event-band','event-duration'])$(id).addEventListener('change',()=>{allEvents=false;if(eventdoc)renderEvents()});
$('more-events').addEventListener('click',()=>{allEvents=true;renderEvents()});
load();
