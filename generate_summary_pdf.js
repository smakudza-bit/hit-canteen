const fs = require('fs');
const path = require('path');

const outPath = path.join(process.cwd(), 'HIT_Canteen_App_Summary.pdf');

const lines = [
  { text: 'HIT Canteen App Summary', size: 22, gap: 28 },
  { text: 'Project overview', size: 13, gap: 18 },
  { text: 'HIT Canteen is a university canteen payment and meal collection platform built with a Django backend and a responsive web frontend for students, staff, and administrators.', size: 11, gap: 14 },
  { text: 'Core student features', size: 13, gap: 18 },
  { text: '- Secure registration, login, and email verification', size: 11, gap: 14 },
  { text: '- Wallet balance, Paynow top up, transaction history, and QR-based meal access', size: 11, gap: 14 },
  { text: '- Meal browsing, cart checkout, QR ticket generation, and profile management', size: 11, gap: 14 },
  { text: 'Core staff features', size: 13, gap: 18 },
  { text: '- Add and manage meals, stock tracking, walk-in orders, and student wallet top ups', size: 11, gap: 14 },
  { text: '- QR scanner for validating student meal tickets and confirming successful collections', size: 11, gap: 14 },
  { text: '- Daily operational tools including served meals, alerts, forecasting, and reconciliation', size: 11, gap: 14 },
  { text: 'Core admin features', size: 13, gap: 18 },
  { text: '- Dashboard for revenue, transactions, reports, students, staff, food items, and system settings', size: 11, gap: 14 },
  { text: '- Exportable reporting, payment diagnostics, and platform oversight across all roles', size: 11, gap: 14 },
  { text: 'Technology and value', size: 13, gap: 18 },
  { text: 'The system combines Django, Django REST Framework, QR verification, wallet accounting, Paynow integration, and mobile-first interface design to make campus meal payments faster, trackable, and easier to manage.', size: 11, gap: 14 },
  { text: 'Outcome', size: 13, gap: 18 },
  { text: 'The app delivers a practical digital canteen workflow: students pay and collect with less friction, staff verify faster, and administrators maintain visibility over finance and operations.', size: 11, gap: 14 },
];

function escapePdf(text) {
  return String(text).replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
}

function wrapText(text, maxChars) {
  const words = text.split(/\s+/);
  const wrapped = [];
  let current = '';
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxChars && current) {
      wrapped.push(current);
      current = word;
    } else {
      current = next;
    }
  }
  if (current) wrapped.push(current);
  return wrapped;
}

let y = 790;
const content = ['BT', '/F1 22 Tf', '50 790 Td'];
let currentSize = 22;
let firstLine = true;

for (const item of lines) {
  const maxChars = item.size >= 13 ? 60 : 95;
  const wrapped = wrapText(item.text, maxChars);
  for (const segment of wrapped) {
    if (!firstLine) {
      content.push(`0 -${item.gap} Td`);
    }
    if (currentSize !== item.size) {
      content.push(`/F1 ${item.size} Tf`);
      currentSize = item.size;
    }
    content.push(`(${escapePdf(segment)}) Tj`);
    y -= item.gap;
    firstLine = false;
  }
}
content.push('ET');
const stream = content.join('\n');

const objects = [];
objects.push('1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj');
objects.push('2 0 obj << /Type /Pages /Count 1 /Kids [3 0 R] >> endobj');
objects.push('3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj');
objects.push('4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj');
objects.push(`5 0 obj << /Length ${Buffer.byteLength(stream, 'utf8')} >> stream\n${stream}\nendstream endobj`);

let pdf = '%PDF-1.4\n';
const offsets = [0];
for (const obj of objects) {
  offsets.push(Buffer.byteLength(pdf, 'utf8'));
  pdf += obj + '\n';
}
const xrefOffset = Buffer.byteLength(pdf, 'utf8');
pdf += `xref\n0 ${objects.length + 1}\n`;
pdf += '0000000000 65535 f \n';
for (let i = 1; i < offsets.length; i++) {
  pdf += `${String(offsets[i]).padStart(10, '0')} 00000 n \n`;
}
pdf += `trailer << /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;

fs.writeFileSync(outPath, pdf, 'binary');
console.log(outPath);
