#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🏥 SIM-REMUNERASI BLUD RSUD MIMIKA - Project Builder
Men-generate seluruh project + ZIP otomatis
Cara pakai: python build_installer.py
"""

import os, zipfile, textwrap
from pathlib import Path

PROJECT_NAME = "sim-remunerasi-rsud-mimika"
OUTPUT_ZIP = f"{PROJECT_NAME}.zip"

# === KONTEN FILE-FILE PROJECT ===
FILES = {
    "requirements.txt": """Flask==2.3.3
Flask-SQLAlchemy==3.0.5
pandas==2.1.0
openpyxl==3.1.2
reportlab==4.0.4
python-dotenv==1.0.0
gunicorn==21.2.0
psycopg2-binary==2.9.9""",

    ".gitignore": """__pycache__/
*.py[cod]
*.db
*.sqlite3
.env
venv/
.DS_Store
*.zip""",

    "config.py": """import os
class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'rsud-mimika-secret-2024')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///database/sim_remunerasi.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024""",

    "database/schema.sql": """-- SIM Remunerasi BLUD RSUD Mimika - Schema
CREATE TABLE IF NOT EXISTS pegawai (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nip VARCHAR(50) UNIQUE NOT NULL,
    nama VARCHAR(100) NOT NULL,
    jabatan VARCHAR(50),
    unit_kerja VARCHAR(50),
    gaji_pokok DECIMAL(12,2),
    role VARCHAR(20) DEFAULT 'pegawai'
);
CREATE TABLE IF NOT EXISTS pendapatan_jasa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bulan INTEGER NOT NULL, tahun INTEGER NOT NULL,
    total_pendapatan DECIMAL(14,2) NOT NULL,
    sumber VARCHAR(30),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS jasa_pegawai (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pegawai_id INTEGER REFERENCES pegawai(id),
    periode_id INTEGER REFERENCES pendapatan_jasa(id),
    jasa_dihasilkan DECIMAL(12,2),
    koefisien DECIMAL(3,2) DEFAULT 1.0
);
CREATE TABLE IF NOT EXISTS indexing_pegawai (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pegawai_id INTEGER REFERENCES pegawai(id),
    periode_id INTEGER REFERENCES pendapatan_jasa(id),
    basic DECIMAL(5,2) DEFAULT 0, kompetensi DECIMAL(5,2) DEFAULT 0,
    risk DECIMAL(5,2) DEFAULT 0, emergency DECIMAL(5,2) DEFAULT 0,
    position DECIMAL(5,2) DEFAULT 0, performance DECIMAL(5,2) DEFAULT 0
);
CREATE TABLE IF NOT EXISTS hasil_remunerasi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pegawai_id INTEGER REFERENCES pegawai(id),
    periode_id INTEGER REFERENCES pendapatan_jasa(id),
    insentif_langsung DECIMAL(12,2) DEFAULT 0,
    insentif_tidak_langsung DECIMAL(12,2) DEFAULT 0,
    total_remunerasi DECIMAL(12,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'draft'
);""",

    "app.py": """from flask import Flask, render_template, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from config import Config
from datetime import datetime
import pandas as pd, io

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)

# === MODELS ===
class Pegawai(db.Model):
    __tablename__ = 'pegawai'
    id = db.Column(db.Integer, primary_key=True)
    nip = db.Column(db.String(50), unique=True, nullable=False)
    nama = db.Column(db.String(100), nullable=False)
    jabatan = db.Column(db.String(50))
    unit_kerja = db.Column(db.String(50))
    gaji_pokok = db.Column(db.Float)
    role = db.Column(db.String(20), default='pegawai')

class PendapatanJasa(db.Model):
    __tablename__ = 'pendapatan_jasa'
    id = db.Column(db.Integer, primary_key=True)
    bulan = db.Column(db.Integer, nullable=False)
    tahun = db.Column(db.Integer, nullable=False)
    total_pendapatan = db.Column(db.Float, nullable=False)
    sumber = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class JasaPegawai(db.Model):
    __tablename__ = 'jasa_pegawai'
    id = db.Column(db.Integer, primary_key=True)
    pegawai_id = db.Column(db.Integer, db.ForeignKey('pegawai.id'))
    periode_id = db.Column(db.Integer, db.ForeignKey('pendapatan_jasa.id'))
    jasa_dihasilkan = db.Column(db.Float)
    koefisien = db.Column(db.Float, default=1.0)

class IndexingPegawai(db.Model):
    __tablename__ = 'indexing_pegawai'
    id = db.Column(db.Integer, primary_key=True)
    pegawai_id = db.Column(db.Integer, db.ForeignKey('pegawai.id'))
    periode_id = db.Column(db.Integer, db.ForeignKey('pendapatan_jasa.id'))
    basic = db.Column(db.Float, default=0); kompetensi = db.Column(db.Float, default=0)
    risk = db.Column(db.Float, default=0); emergency = db.Column(db.Float, default=0)
    position = db.Column(db.Float, default=0); performance = db.Column(db.Float, default=0)
    @property
    def total_score(self):
        return self.basic + self.kompetensi + self.risk + self.emergency + self.position + self.performance

class HasilRemunerasi(db.Model):
    __tablename__ = 'hasil_remunerasi'
    id = db.Column(db.Integer, primary_key=True)
    pegawai_id = db.Column(db.Integer, db.ForeignKey('pegawai.id'))
    periode_id = db.Column(db.Integer, db.ForeignKey('pendapatan_jasa.id'))
    insentif_langsung = db.Column(db.Float, default=0)
    insentif_tidak_langsung = db.Column(db.Float, default=0)
    total_remunerasi = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default='draft')

# === ROUTES ===
@app.route('/')
def dashboard():
    total = db.session.query(db.func.sum(PendapatanJasa.total_pendapatan)).scalar() or 0
    return render_template('dashboard.html', total_pendapatan=total)

@app.route('/api/hitung_alokasi', methods=['POST'])
def hitung_alokasi():
    data = request.json
    total = float(data.get('total_pendapatan', 0))
    persen = float(data.get('persen_remun', 0.35))
    dana_remun = total * persen
    return jsonify({
        'dana_remunerasi': round(dana_remun, 2),
        'insentif_langsung': round(dana_remun * 0.6, 2),
        'pos_remunerasi': round(dana_remun * 0.4, 2),
        'dana_operasional': round(total - dana_remun, 2)
    })

@app.route('/api/hitung_langsung', methods=['POST'])
def hitung_langsung():
    items = request.json.get('items', [])
    hasil = []
    for i in items:
        jasa = float(i.get('jasa_dihasilkan', 0))
        koef = float(i.get('koefisien', 1.0))
        hasil.append({'pegawai_id': i['pegawai_id'], 'insentif_langsung': round(jasa * 0.6 * koef, 2)})
    return jsonify(hasil)

@app.route('/api/hitung_indexing', methods=['POST'])
def hitung_indexing():
    items = request.json.get('items', [])
    pos_dana = float(request.json.get('pos_remunerasi', 0))
    total_score = sum(sum(i['scores'].values()) for i in items)
    hasil = []
    for i in items:
        score = sum(i['scores'].values())
        insentif_tl = (score / total_score * pos_dana) if total_score > 0 else 0
        hasil.append({'pegawai_id': i['pegawai_id'], 'total_score': round(score, 2), 'insentif_tidak_langsung': round(insentif_tl, 2)})
    return jsonify(hasil)

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True, port=5000)""",

    "templates/base.html": """<!DOCTYPE html>
<html lang="id"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SIM-REMUNERASI RSUD MIMIKA</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="{{ url_for('static', filename='css/style.css') }}" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script></head>
<body><nav class="navbar navbar-expand-lg navbar-dark bg-primary"><div class="container">
<a class="navbar-brand" href="/">🏥 SIM-REM BLUD</a>
<button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav"><span class="navbar-toggler-icon"></span></button>
<div class="collapse navbar-collapse" id="navbarNav"><ul class="navbar-nav ms-auto">
<li class="nav-item"><a class="nav-link" href="/">Dashboard</a></li>
<li class="nav-item"><a class="nav-link" href="/indexing">Indexing</a></li>
<li class="nav-item"><a class="nav-link" href="/hasil">Hasil</a></li>
</ul></div></div></nav>
<main class="container mt-4">{% with messages = get_flashed_messages() %}{% if messages %}{% for message in messages %}<div class="alert alert-info">{{ message }}</div>{% endfor %}{% endif %}{% endwith %}{% block content %}{% endblock %}</main>
<footer class="text-center py-3 text-muted small">&copy; 2024 BLUD RSUD Mimika | Perbup No. 32/2023</footer>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="{{ url_for('static', filename='js/calc_engine.js') }}"></script></body></html>""",

    "templates/dashboard.html": """{% extends "base.html" %}{% block content %}
<div class="row"><div class="col-12 mb-4"><h2>📊 Dashboard Remunerasi</h2></div></div>
<div class="row g-3">
<div class="col-md-3"><div class="card bg-primary text-white"><div class="card-body"><h6>Total Pendapatan</h6><h3>Rp {{ "{:,.0f}".format(total_pendapatan) }}</h3></div></div></div>
<div class="col-md-3"><div class="card bg-success text-white"><div class="card-body"><h6>Dana Remunerasi</h6><h3 id="dana-remun">Rp 0</h3></div></div></div>
<div class="col-md-3"><div class="card bg-warning text-dark"><div class="card-body"><h6>Insentif Langsung</h6><h3 id="insentif-langsung">Rp 0</h3></div></div></div>
<div class="col-md-3"><div class="card bg-info text-white"><div class="card-body"><h6>Pos Remunerasi</h6><h3 id="pos-remun">Rp 0</h3></div></div></div>
</div>
<div class="row mt-4"><div class="col-md-6"><canvas id="chartAlokasi"></canvas></div><div class="col-md-6"><canvas id="chartDistribusi"></canvas></div></div>
<script>
document.addEventListener('DOMContentLoaded', function() {
    const totalPendapatan = {{ total_pendapatan }};
    fetch('/api/hitung_alokasi', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({total_pendapatan: totalPendapatan})})
    .then(res => res.json()).then(data => {
        document.getElementById('dana-remun').textContent = 'Rp ' + data.dana_remunerasi.toLocaleString('id-ID');
        document.getElementById('insentif-langsung').textContent = 'Rp ' + data.insentif_langsung.toLocaleString('id-ID');
        document.getElementById('pos-remun').textContent = 'Rp ' + data.pos_remunerasi.toLocaleString('id-ID');
        new Chart(document.getElementById('chartAlokasi'), {type: 'doughnut', data: {labels: ['Operasional', 'Remunerasi'], datasets: [{data: [data.dana_operasional, data.dana_remunerasi], backgroundColor: ['#6c757d', '#198754']}]}});
        new Chart(document.getElementById('chartDistribusi'), {type: 'pie', data: {labels: ['Langsung', 'Tidak Langsung'], datasets: [{data: [data.insentif_langsung, data.pos_remunerasi], backgroundColor: ['#ffc107', '#0dcaf0']}]}});
    });
});
</script>{% endblock %}""",

    "templates/indexing.html": """{% extends "base.html" %}{% block content %}
<h2>🎯 Input Indexing Pegawai</h2><p class="text-muted">Periode: <strong>{{ bulan }} {{ tahun }}</strong></p>
<form id="formIndexing"><div class="table-responsive"><table class="table table-bordered"><thead class="table-light"><tr><th>Pegawai</th><th>Basic</th><th>Kompetensi</th><th>Risk</th><th>Emergency</th><th>Position</th><th>Performance</th><th>Total</th></tr></thead>
<tbody id="tbodyIndexing"></tbody></table></div>
<button type="button" class="btn btn-primary" onclick="hitungIndexing()">💰 Hitung</button>
<button type="button" class="btn btn-success" onclick="simpanHasil()">💾 Simpan</button></form>
<div id="hasilIndexing" class="mt-4 d-none"><h4>📋 Hasil</h4><div class="table-responsive"><table class="table table-striped"><thead><tr><th>Pegawai</th><th>Score</th><th>Insentif</th></tr></thead><tbody id="tbodyHasil"></tbody></table></div></div>
<script>
const pegawaiList = {{ pegawai_json | safe }}; const posRemunerasi = {{ pos_remunerasi }};
function renderForm() {
    const tbody = document.getElementById('tbodyIndexing'); tbody.innerHTML = '';
    pegawaiList.forEach(p => {
        const basic = Math.floor(p.gaji_pokok / 500000);
        tbody.innerHTML += `<tr data-id="${p.id}"><td>${p.nama}<br><small class="text-muted">${p.jabatan}</small></td>`+
        ['basic','kompetensi','risk','emergency','position','performance'].map(f=>`<td><input type="number" class="form-control score-input" data-field="${f}" value="${f==='basic'?basic:0}" min="0"></td>`).join('')+
        `<td class="total-score fw-bold">0</td></tr>`;
    });
    document.querySelectorAll('.score-input').forEach(inp => inp.addEventListener('input', calcRowScore));
}
function calcRowScore(e) { const row = e.target.closest('tr'); let total = 0; row.querySelectorAll('.score-input').forEach(inp => total += parseFloat(inp.value)||0); row.querySelector('.total-score').textContent = total.toFixed(2); }
async function hitungIndexing() {
    const items = []; document.querySelectorAll('#tbodyIndexing tr').forEach(row => {
        const scores = {}; row.querySelectorAll('.score-input').forEach(inp => scores[inp.dataset.field] = parseFloat(inp.value)||0);
        items.push({pegawai_id: row.dataset.id, scores});
    });
    const res = await fetch('/api/hitung_indexing', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({items, pos_remunerasi: posRemunerasi})});
    const hasil = await res.json(); const tbody = document.getElementById('tbodyHasil'); tbody.innerHTML = '';
    hasil.forEach(h => { const p = pegawaiList.find(x => x.id == h.pegawai_id); tbody.innerHTML += `<tr><td>${p.nama}</td><td>${h.total_score}</td><td>Rp ${h.insentif_tidak_langsung.toLocaleString('id-ID')}</td></tr>`; });
    document.getElementById('hasilIndexing').classList.remove('d-none');
}
function simpanHasil() { alert('✅ Data disimpan (implementasi backend diperlukan)'); }
document.addEventListener('DOMContentLoaded', renderForm);
</script>{% endblock %}""",

    "static/css/style.css": """body { background-color: #f8f9fa; font-family: 'Segoe UI', sans-serif; }
.card { border: none; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.navbar-brand { font-weight: 600; }
.table th { font-weight: 600; background-color: #e9ecef; }
.btn-primary { background-color: #0d6efd; border: none; }
.btn-primary:hover { background-color: #0b5ed7; }
.alert { border-left: 4px solid #0dcaf0; }
footer { border-top: 1px solid #dee2e6; margin-top: 3rem; }""",

    "static/js/calc_engine.js": """window.RemunCalculator = {
    hitungBasicIndex: function(gajiPokok) { return Math.floor(gajiPokok / 500000); },
    hitungInsentifLangsung: function(jasa, koefisien) { return jasa * 0.6 * koefisien; },
    formatRupiah: function(angka) { return new Intl.NumberFormat('id-ID', {style: 'currency', currency: 'IDR'}).format(angka); },
    validateInput: function(data) { return data.total_pendapatan && data.total_pendapatan > 0; }
};""",

    "docs/README.md": """# 💰 SIM-REMUNERASI BLUD RSUD MIMIKA
*Sistem Informasi Perhitungan & Pembagian Remunerasi berbasis Perbup Mimika No. 32/2023*

## 🚀 Quick Start
```bash
# 1. Ekstrak ZIP
unzip sim-remunerasi-rsud-mimika.zip
cd sim-remunerasi-rsud-mimika

# 2. Install dependencies
pip install -r requirements.txt

# 3. Jalankan aplikasi
python app.py

# 4. Akses: http://localhost:5000