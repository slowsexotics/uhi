/* All AI/profile/feedback text is rendered as text, never HTML. */
(() => {
  'use strict';
  const el = id => document.getElementById(id);
  let rows = [], selected = null, generationKey = null, feedbackRetry = null;
  const message = text => { el('creator-message').textContent = text; };
  const key = () => crypto.randomUUID();
  async function api(path, data) {
    const response = await fetch(path, data === undefined ? {} : {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data)
    });
    const result = await response.json();
    if (!response.ok || result.status !== 'ok') throw new Error(result.message || 'UHI could not complete this operation.');
    return result;
  }
  function paragraph(container, label, text) {
    const section = document.createElement('section');
    const heading = document.createElement('h3'); heading.textContent = label;
    const body = document.createElement('p'); body.textContent = text;
    section.append(heading, body); container.append(section);
  }
  function render(row) {
    selected = row;
    const box = el('creator-briefing-content'); box.replaceChildren();
    el('creator-feedback').hidden = !row || row.generation_status !== 'generated';
    if (!row) { paragraph(box,'Start here','Save your interests and goals in your profile, then generate your first briefing.'); return; }
    if (row.generation_status !== 'generated') {
      paragraph(box,'Briefing not completed',row.error || 'Generation is in progress. No completed briefing has been saved.'); return;
    }
    const content = row.content;
    paragraph(box,'Your context',content.personal_context);
    paragraph(box,'One action for today',content.recommended_action);
    paragraph(box,'Why it fits you',content.why);
    const list = document.createElement('ol');
    content.steps.forEach(text => { const item=document.createElement('li'); item.textContent=text; list.append(item); });
    box.append(list);
    paragraph(box,'What completing it looks like',content.done_when);
    paragraph(box,'One question for you',content.question);
    el('creator-response').value=row.user_response || '';
    el('creator-obstacle').value=row.feedback || '';
    el('creator-progress').value=row.completion_status;
    feedbackRetry=null;
  }
  async function load(prefer) {
    try {
      const data=await api('/api/creator/briefings'); rows=data.briefings;
      const select=el('creator-history'); select.replaceChildren();
      rows.forEach(row => {
        const option=document.createElement('option'); option.value=row.id;
        option.textContent=new Date(row.created_at).toLocaleString()+' · '+row.generation_status+' · '+row.completion_status;
        select.append(option);
      });
      const row=rows.find(x=>x.id===prefer) || rows[0] || null;
      if (row) select.value=row.id;
      render(row);
    } catch (error) { message(error.message); }
  }
  el('creator-history').addEventListener('change', event => render(rows.find(x=>x.id===event.target.value)));
  el('creator-generate').addEventListener('click', async () => {
    const button=el('creator-generate'); button.disabled=true;
    generationKey=generationKey || key(); sessionStorage.setItem('uhi-generation-request', generationKey); message('Generating your briefing. This may take up to 90 seconds.');
    try {
      const data=await api('/api/creator/briefings/generate',{request_id:generationKey});
      generationKey=null;
      await load(data.briefing.id);
      message('Briefing generated and saved. Your task stays in progress until you update it.');
    } catch (error) {
      message(error.message);
      // Preserve the retry identifier even across a page reload or dropped response.
      await load();
    } finally {
      sessionStorage.setItem('uhi-generation-request', generationKey || '');
      button.disabled=false;
    }
  });
  el('creator-feedback').addEventListener('submit', async event => {
    event.preventDefault();
    if (!selected) return;
    const button=el('creator-save-feedback'); button.disabled=true;
    const values={briefing_id:selected.id,response:el('creator-response').value,
      feedback:el('creator-obstacle').value,completion_status:el('creator-progress').value};
    const fingerprint=JSON.stringify(values);
    if (!feedbackRetry || feedbackRetry.fingerprint!==fingerprint) feedbackRetry={fingerprint,event_id:key()};
    try {
      const data=await api('/api/creator/briefings/feedback',{...values,event_id:feedbackRetry.event_id});
      feedbackRetry=null;
      // New action after confirmed feedback gets a fresh generation snapshot.
      generationKey=null; sessionStorage.removeItem('uhi-generation-request');
      await load(data.briefing.id);
      message('Answer and progress saved. Your next briefing will receive this learning.');
    } catch (error) { message(error.message); }
    finally { button.disabled=false; }
  });
  window.addEventListener('uhi-profile-saved', () => { generationKey=null; sessionStorage.removeItem('uhi-generation-request'); });
  generationKey=sessionStorage.getItem('uhi-generation-request') || null;
  window.loadCreatorBriefings=load;
  load();
})();
