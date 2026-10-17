'use strict';
const $ = id => document.getElementById(id);
const et = value => value ? new Date(value).toLocaleString('en-US',{timeZone:'America/New_York',dateStyle:'medium',timeStyle:'short'}) : 'Not available';
let summary;
function renderWindow(){
  const item=summary.windows[$('window').value];
  $('window-label').textContent=`${et(item.start)} to ${et(item.end)} Eastern. Missing time is excluded from statistics.`;
  for(const channel of ['HDF','EHZ']){
    const c=item.channels[channel], key=channel.toLowerCase();
    $(key+'-minutes').textContent=c.complete_minutes.toLocaleString();
    if(channel==='HDF'){
      $('hdf-band').textContent=c.complete_minutes ? c.band_minutes.toLocaleString() : 'Not measured';
      $('hdf-run').textContent=c.complete_minutes ? c.longest_run_minutes : '—';
    } else $('ehz-coverage').textContent=c.coverage_pct===null?'—':c.coverage_pct.toFixed(1)+'%';
  }
}
async function load(){
  try{
    const responses=await Promise.all(['status','summary'].map(n=>fetch(`data/${n}.json`,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(`HTTP ${r.status}`);return r.json()})));
    const status=responses[0]; summary=responses[1];
    if(status.station!=='AM.R19BB.00'||summary.station!==status.station)throw Error('Station identity mismatch');
    const stale=Date.now()-Date.parse(status.generated_utc)>26*3600000;
    $('state').textContent=stale?'Snapshot stale':status.state;
    $('status-note').textContent=stale?'The last check is more than 26 hours old. Do not interpret this snapshot as current connectivity.':status.note;
    $('updated').textContent=et(status.generated_utc);
    $('attempts').replaceChildren();
    for(const c of status.channels){
      const tr=document.createElement('tr');
      for(const value of [c.channel,c.error||`${c.complete_minutes} complete minutes accepted`,et(c.latest_sample_utc)]){
        const td=document.createElement('td');td.textContent=value;tr.append(td);
      }
      $('attempts').append(tr);
    }
    $('timeline').replaceChildren();
    for(const channel of ['HDF','EHZ']){
      const track=document.createElement('div');track.className='track';
      const name=document.createElement('span');name.className='track-label';name.textContent=channel;track.append(name);
      for(const h of summary.hours){
        const cell=document.createElement('div');cell.className='hour';cell.tabIndex=0;
        const n=h.channels[channel], label=`${channel}: ${et(h.start)} Eastern, ${n} of 60 complete minutes`;
        cell.title=label;cell.setAttribute('aria-label',label);
        if(n)cell.style.background=`rgba(85,228,156,${.12+.88*n/60})`;
        track.append(cell);
      }
      $('timeline').append(track);
    }
    const axis=document.createElement('div');axis.className='axis';
    for(const value of [et(summary.hours[0]?.start),et(summary.hours.at(-1)?.start)]){
      const span=document.createElement('span');span.textContent=value;axis.append(span);
    }
    $('timeline').append(axis);renderWindow();
  }catch(error){
    $('state').textContent='Snapshot unavailable';
    $('status-note').textContent=`Could not validate the dashboard data (${error.message}). No online status or measurement totals can be confirmed.`;
  }
}
$('window').addEventListener('change',()=>{if(summary)renderWindow()});
load();
