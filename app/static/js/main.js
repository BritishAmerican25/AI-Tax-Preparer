/* ── Income rows ────────────────────────────────────────────── */
let incomeCount = 0;

/* ── Configuration constants ────────────────────────────────── */
const AI_INITIAL_QUESTION =
  'Please give me a brief, friendly overview of my tax situation and the top 2 things I can do to optimize my taxes.';

function addIncomeRow(sourceType = 'W-2', payer = '', gross = '', withheld = '') {
  incomeCount++;
  const id = incomeCount;
  const types = ['W-2','1099-NEC','1099-MISC','1099-INT','1099-DIV','1099-R','1099-G','K-1','Other'];
  const opts = types.map(t => `<option value="${t}" ${t === sourceType ? 'selected' : ''}>${t}</option>`).join('');

  const html = `
    <div class="income-row" id="income-${id}">
      <button class="remove-btn" onclick="removeIncomeRow(${id})" title="Remove">✕</button>
      <div class="row-3">
        <div class="field-group">
          <label>Form Type</label>
          <select class="inc-type" data-id="${id}">${opts}</select>
        </div>
        <div class="field-group">
          <label>Gross Amount ($)</label>
          <input type="number" class="inc-gross" data-id="${id}" min="0" step="1" value="${gross}" placeholder="0" />
        </div>
        <div class="field-group">
          <label>Federal Tax Withheld ($)</label>
          <input type="number" class="inc-withheld" data-id="${id}" min="0" step="1" value="${withheld}" placeholder="0" />
        </div>
      </div>
      <div class="row-2b">
        <div class="field-group">
          <label>Employer / Payer Name</label>
          <input type="text" class="inc-payer" data-id="${id}" value="${payer}" placeholder="e.g. ACME Corp" />
        </div>
      </div>
    </div>`;
  document.getElementById('income-list').insertAdjacentHTML('beforeend', html);
}

function removeIncomeRow(id) {
  const el = document.getElementById(`income-${id}`);
  if (el) el.remove();
}

/* ── Step navigation ────────────────────────────────────────── */
function goStep(n) {
  [1,2,3,4].forEach(i => {
    document.getElementById(`step-${i}`).classList.toggle('hidden', i !== n);
    const ind = document.getElementById(`step-indicator-${i}`);
    ind.classList.remove('active', 'done');
    if (i === n) ind.classList.add('active');
    if (i < n)  ind.classList.add('done');
  });
}

/* ── Filing status: show/hide spouse age ────────────────────── */
document.getElementById('filing_status').addEventListener('change', function () {
  const needSpouse = ['married_filing_jointly', 'qualifying_surviving_spouse'].includes(this.value);
  document.getElementById('spouse-age-wrap').style.display = needSpouse ? '' : 'none';
});

/* ── Format currency ────────────────────────────────────────── */
function fmt(n) {
  if (n === undefined || n === null) return '–';
  const abs = Math.abs(n);
  const str = abs.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  return n < 0 ? `-${str}` : str;
}
function fmtPct(n) { return (n * 100).toFixed(1) + '%'; }

/* ── Collect form data ──────────────────────────────────────── */
function collectPayload() {
  const v = id => document.getElementById(id);
  const num = id => parseFloat(v(id).value) || 0;

  // Income sources
  const rows = document.querySelectorAll('.income-row');
  if (rows.length === 0) {
    return { error: 'Add at least one income source.' };
  }
  const income_sources = [];
  for (const row of rows) {
    const rid = row.dataset.id || row.id.replace('income-', '');
    const payer = row.querySelector('.inc-payer').value.trim();
    if (!payer) return { error: 'Payer name is required for each income source.' };
    income_sources.push({
      source_type:          row.querySelector('.inc-type').value,
      employer_or_payer:    payer,
      gross_amount:         parseFloat(row.querySelector('.inc-gross').value) || 0,
      federal_tax_withheld: parseFloat(row.querySelector('.inc-withheld').value) || 0,
    });
  }

  const filing_status = v('filing_status').value;
  const taxpayer_age  = parseInt(v('taxpayer_age').value) || 35;
  const spouse_age    = ['married_filing_jointly', 'qualifying_surviving_spouse'].includes(filing_status)
                          ? (parseInt(v('spouse_age').value) || 35) : undefined;
  const tax_year      = parseInt(v('tax_year').value) || 2024;

  return {
    tax_year,
    filing_status,
    taxpayer_age,
    ...(spouse_age !== undefined && { spouse_age }),
    number_of_dependents: parseInt(v('dependents').value) || 0,
    income_sources,
    deductions: {
      mortgage_interest:      num('mortgage_interest'),
      state_local_taxes:      num('salt'),
      charitable_contributions: num('charitable'),
      medical_expenses_total: num('medical'),
      student_loan_interest:  num('student_loan'),
      other_deductions:       0,
    },
    credits: {
      child_tax_credit_dependents: parseInt(v('child_dependents').value) || 0,
      earned_income_credit:        num('eitc'),
      child_and_dependent_care:    num('child_care'),
      education_credits:           num('education'),
      retirement_savings_credit:   num('retirement_credit'),
      other_credits:               num('other_credits'),
    },
    use_itemized_deductions:              v('use_itemized').checked,
    self_employment_income:               num('se_income'),
    retirement_contributions_traditional: num('retirement'),
    health_savings_account_contribution:  num('hsa'),
    // OBBBA 2026 fields
    obbba_overtime_premium:     num('obbba_overtime'),
    obbba_tips:                 num('obbba_tips'),
    obbba_car_vin:              v('obbba_car_vin')?.value || null,
    obbba_car_interest_paid:    num('obbba_car_interest'),
    obbba_child_dob:            v('obbba_child_dob')?.value || null,
    obbba_child_has_ssn:        v('obbba_child_ssn')?.checked || false,
  };
}

/* ── Set loading state ──────────────────────────────────────── */
function setLoading(on) {
  const btn = document.getElementById('submit-btn');
  btn.querySelector('.btn-text').classList.toggle('hidden', on);
  btn.querySelector('.btn-spinner').classList.toggle('hidden', !on);
  btn.disabled = on;
}

/* ── Render Phase 1 results ─────────────────────────────────── */
function renderCalc(r) {
  const hero = document.getElementById('refund-hero');
  hero.className = 'refund-hero';
  const refund = r.refund_or_owed;
  if (refund > 0) {
    hero.classList.add('refund');
    document.getElementById('refund-label').textContent = 'Estimated Refund';
    document.getElementById('refund-amount').textContent = fmt(refund);
  } else if (refund < 0) {
    hero.classList.add('owed');
    document.getElementById('refund-label').textContent = 'Amount You Owe';
    document.getElementById('refund-amount').textContent = fmt(Math.abs(refund));
  } else {
    document.getElementById('refund-label').textContent = 'No Refund / No Balance Due';
    document.getElementById('refund-amount').textContent = '$0';
  }

  document.getElementById('r-gross').textContent    = fmt(r.gross_income);
  document.getElementById('r-agi').textContent      = fmt(r.adjusted_gross_income);
  document.getElementById('r-deduction').textContent =
    r.deduction_used === 'itemized'
      ? `Itemized (${fmt(r.itemized_deduction_total)})`
      : `Standard (${fmt(r.standard_deduction)})`;
  document.getElementById('r-taxable').textContent  = fmt(r.taxable_income);
  document.getElementById('r-tax').textContent      = fmt(r.federal_tax_owed);
  document.getElementById('r-se').textContent       = r.self_employment_tax > 0 ? fmt(r.self_employment_tax) : '—';
  document.getElementById('r-credits').textContent  = r.total_credits > 0 ? fmt(r.total_credits) : '—';
  document.getElementById('r-withheld').textContent = fmt(r.total_federal_tax_withheld);

  // Rate bars (max visual at 37%)
  const eff = r.effective_tax_rate;
  const mar = r.marginal_tax_rate;
  document.getElementById('bar-effective').style.width = Math.min(eff / 0.37 * 100, 100) + '%';
  document.getElementById('bar-marginal').style.width  = Math.min(mar / 0.37 * 100, 100) + '%';
  document.getElementById('pct-effective').textContent = fmtPct(eff);
  document.getElementById('pct-marginal').textContent  = fmtPct(mar);

  // Bracket table
  const tbody = document.getElementById('bracket-tbody');
  tbody.innerHTML = '';
  (r.breakdown_by_bracket || []).forEach(b => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><strong>${b.rate}</strong></td><td>${fmt(b.income_in_bracket)}</td><td>${fmt(b.tax_in_bracket)}</td>`;
    tbody.appendChild(tr);
  });

  // OBBBA 2026 Summary
  const hasOBBBA = r.obbba_no_tax_overtime > 0 || r.obbba_no_tax_tips > 0 ||
                   r.obbba_car_interest_deduction > 0 || r.obbba_trump_account_info;
  const obbbaSummary = document.getElementById('obbba-summary');
  if (hasOBBBA) {
    obbbaSummary.style.display = 'block';
    document.getElementById('obbba-ot').textContent = fmt(r.obbba_no_tax_overtime || 0);
    document.getElementById('obbba-tips').textContent = fmt(r.obbba_no_tax_tips || 0);
    document.getElementById('obbba-car').textContent = fmt(r.obbba_car_interest_deduction || 0);

    const carMsg = document.getElementById('obbba-car-msg');
    if (r.obbba_car_eligibility_message) {
      carMsg.textContent = 'Car: ' + r.obbba_car_eligibility_message;
    } else {
      carMsg.textContent = '';
    }

    const trumpDiv = document.getElementById('obbba-trump');
    if (r.obbba_trump_account_info && r.obbba_trump_account_info.federal_seed_eligible) {
      trumpDiv.textContent = '✓ Trump Account eligible for $1,000 federal seed';
    } else if (r.obbba_trump_account_info) {
      trumpDiv.textContent = 'Trump Account not eligible (check requirements)';
    } else {
      trumpDiv.textContent = '';
    }
  } else {
    obbbaSummary.style.display = 'none';
  }
}

/* ── Render Phase 2 compliance ──────────────────────────────── */
function renderCompliance(c) {
  // Gauge
  const score = c.audit_risk_score;           // 0–1
  const totalArc = 251.2;                      // full semi-circle circumference
  const offset = totalArc - score * totalArc;
  document.getElementById('gauge-fill').style.strokeDashoffset = offset;

  // Needle: -90° = left (0), +90° = right (1)
  const deg = -90 + score * 180;
  document.getElementById('gauge-needle').setAttribute('transform', `rotate(${deg},100,100)`);
  document.getElementById('gauge-label').textContent = c.audit_risk_label;

  // Status
  const passed = c.passed;
  document.getElementById('status-icon').textContent = passed ? '✅' : '❌';
  document.getElementById('status-text').textContent = passed ? 'No compliance issues found' : `${c.issues.length} issue(s) detected`;

  // Issues
  const iw = document.getElementById('issues-wrap');
  const il = document.getElementById('issues-list');
  if (c.issues && c.issues.length) {
    iw.classList.remove('hidden');
    il.innerHTML = c.issues.map(i => `<li>${i}</li>`).join('');
  } else {
    iw.classList.add('hidden');
  }

  // Warnings
  const ww = document.getElementById('warnings-wrap');
  const wl = document.getElementById('warnings-list');
  if (c.warnings && c.warnings.length) {
    ww.classList.remove('hidden');
    wl.innerHTML = c.warnings.map(w => `<li>${w}</li>`).join('');
  } else {
    ww.classList.add('hidden');
  }

  // Recommendations
  const rw = document.getElementById('recs-wrap');
  const rl = document.getElementById('recs-list');
  if (c.recommendations && c.recommendations.length) {
    rw.classList.remove('hidden');
    rl.innerHTML = c.recommendations.map(r => `<li>${r}</li>`).join('');
  } else {
    rw.classList.add('hidden');
  }
}

/* ── Render Phase 3 AI response ─────────────────────────────── */
function appendChat(role, text) {
  const win = document.getElementById('chat-window');
  const div = document.createElement('div');
  div.className = `chat-msg ${role}`;
  div.textContent = text;
  win.appendChild(div);
  win.scrollTop = win.scrollHeight;
  return div;
}

function setDisclaimer(text) {
  document.getElementById('ai-disclaimer').textContent = text;
}

/* ── Stored payload for follow-up chat ──────────────────────── */
let _lastPayload = null;

/* ── Main form submit ───────────────────────────────────────── */
document.getElementById('tax-form').addEventListener('submit', async function (e) {
  e.preventDefault();

  const payload = collectPayload();
  if (payload.error) {
    showError(payload.error);
    return;
  }
  _lastPayload = payload;
  hideError();
  setLoading(true);

  try {
    const fullPayload = { ...payload, question: AI_INITIAL_QUESTION };

    const res = await fetch('/api/v1/full', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fullPayload),
    });

    const data = await res.json();

    if (!res.ok) {
      const detail = data.details ? data.details.map(d => d.msg).join('; ') : (data.error || 'Unknown error');
      showError(detail);
      setLoading(false);
      return;
    }

    // Show results panel
    document.getElementById('empty-state').classList.add('hidden');
    document.getElementById('results-body').classList.remove('hidden');

    renderCalc(data.tax_calculation);
    renderCompliance(data.compliance_review);

    // AI welcome
    document.getElementById('chat-window').innerHTML = '';
    appendChat('assistant', data.ai_assistant.answer);
    setDisclaimer(data.ai_assistant.disclaimer);

  } catch (err) {
    showError('Could not reach the server. Is it running?');
  }

  setLoading(false);
});

/* ── AI follow-up chat ──────────────────────────────────────── */
async function sendQuestion() {
  const input = document.getElementById('chat-input');
  const q = input.value.trim();
  if (!q) return;
  input.value = '';

  appendChat('user', q);
  const typing = appendChat('assistant typing', '…');

  try {
    const body = { question: q };
    if (_lastPayload) body.return_data = _lastPayload;

    const res = await fetch('/api/v1/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    typing.remove();

    if (!res.ok) {
      appendChat('assistant', '⚠ Error: ' + (data.error || 'Unknown error'));
    } else {
      appendChat('assistant', data.answer);
      if (data.disclaimer) setDisclaimer(data.disclaimer);
    }
  } catch {
    typing.remove();
    appendChat('assistant', '⚠ Could not reach the server.');
  }
}

document.getElementById('chat-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') sendQuestion();
});

/* ── Error helpers ──────────────────────────────────────────── */
function showError(msg) {
  const b = document.getElementById('error-banner');
  document.getElementById('error-text').textContent = msg;
  b.classList.remove('hidden');
}
function hideError() {
  document.getElementById('error-banner').classList.add('hidden');
}

/* ── OBBBA fields toggle ────────────────────────────────────── */
function toggleOBBBAFields() {
  const taxYear = parseInt(document.getElementById('tax_year').value);
  const obbbFields = document.getElementById('obbba-fields');
  const yearBadge = document.getElementById('year-badge');

  if (taxYear >= 2026) {
    obbbFields.style.display = 'block';
    yearBadge.textContent = '2026 Federal Return (OBBBA)';
  } else {
    obbbFields.style.display = 'none';
    yearBadge.textContent = '2024 Federal Return';
  }
}

/* ── Init: add first income row (empty, ready for user input) ── */
addIncomeRow();
