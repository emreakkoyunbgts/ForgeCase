import React from 'react';
import { Link, Routes, Route } from 'react-router-dom';
import Sidebar from './Sidebar';
import UploadRecord from './UploadRecord';
import Engagments from "./Engagements.jsx";
import EngagementDetail from "./EngagementDetail.jsx";
import EditEngagement from "./EditEngagement.jsx";
import Query from "./Query.jsx";
import Analyze from "./Analyze.jsx";
import './App.css';

function Home() {
  return (
    <main className="home-page">
      <section className="home-hero">
        <div className="hero-copy">
          <span className="eyebrow">ENGAGEMENT INTELLIGENCE</span>
          <h1>Record’lardan güçlü case study’lere, tek akışta.</h1>
          <p>
            Dokümanlarınızı yapılandırılmış kayıtlara dönüştürün; inceleyin,
            yönetin ve ihtiyacınıza en uygun başarı hikâyesini yapay zekâ ile üretin.
          </p>
          <div className="hero-actions">
            <Link className="primary-action" to="/upload-record">Record yükle <span>→</span></Link>
            <Link className="secondary-action" to="/query">Case study oluştur</Link>
          </div>
        </div>
        <div className="workflow-preview" aria-label="Uygulama iş akışı">
          <div className="preview-top"><span className="status-dot" /> Canlı iş akışı</div>
          <div className="preview-row"><span className="preview-icon upload-icon">↑</span><div><b>PDF Record</b><small>Doküman yüklendi</small></div><span className="preview-check">✓</span></div>
          <div className="preview-line" />
          <div className="preview-row"><span className="preview-icon review-icon">⌕</span><div><b>Ön izleme</b><small>Alanlar gözden geçirildi</small></div><span className="preview-check">✓</span></div>
          <div className="preview-line" />
          <div className="preview-row active"><span className="preview-icon ai-icon">✦</span><div><b>AI Case Study</b><small>İçerik üretiliyor</small></div><span className="preview-pulse" /></div>
        </div>
      </section>

      <section className="journey-section">
        <div className="section-heading">
          <span className="eyebrow">NASIL ÇALIŞIR?</span>
          <h2>İçeriğinizi karar vermeye hazır bilgiye dönüştürün.</h2>
        </div>
        <div className="journey-grid">
          <article className="journey-card"><span className="step-number">01</span><span className="journey-icon">↥</span><h3>Upload</h3><p>PDF record’u yükleyin. Sistem dokümandaki bilgileri çıkarır ve yapılandırılmış bir record taslağı hazırlar.</p><Link to="/upload-record">Record yükle →</Link></article>
          <article className="journey-card"><span className="step-number">02</span><span className="journey-icon">◌</span><h3>Gözlemle ve kaydet</h3><p>Çıkarılan bilgileri önce ön izleme ekranında kontrol edin. Doğruluğundan emin olduğunuz record’u sonra kaydedin.</p><Link to="/upload-record">Ön izlemeye git →</Link></article>
          <article className="journey-card"><span className="step-number">03</span><span className="journey-icon">✎</span><h3>Record’ları yönet</h3><p>Engagements alanında kayıtları görüntüleyin; ihtiyaç halinde detaylarını düzenleyin veya artık gerekli olmayan record’ları silin.</p><Link to="/engagements">Record’ları yönet →</Link></article>
          <article className="journey-card"><span className="step-number">04</span><span className="journey-icon">✦</span><h3>Case study üret</h3><p>Yapay zekâ, seçilen record’ların bağlamını kullanarak tutarlı, kaynaklanabilir case study içerikleri oluşturur.</p><Link to="/query">Üretime başla →</Link></article>
        </div>
      </section>

      <section className="insights-section">
        <div className="insight-copy">
          <span className="eyebrow">ANALYZE</span>
          <h2>Portföyünüzde ne var, ne eksik?</h2>
          <p>Analyze, kayıt havuzunuzu domain, bölge ve müşteri türüne göre görünür kılar. Coverage analizi mevcut kapsama alanınızı özetler; Gap analizi ise henüz record bulunmayan domain–bölge kombinasyonlarını işaretler.</p>
          <p className="insight-note">Böylece yeni içerik toplamanız gereken alanları kolayca belirleyebilir, case study havuzunuzu dengeli büyütebilirsiniz.</p>
          <Link className="text-action" to="/analyze">Analizi görüntüle <span>→</span></Link>
        </div>
        <div className="insight-panel">
          <div className="panel-title"><span>Coverage overview</span><b>Güncel</b></div>
          <div className="coverage-bars"><div><label>Finans <em>8 record</em></label><i><b style={{width: '86%'}} /></i></div><div><label>Perakende <em>5 record</em></label><i><b style={{width: '57%'}} /></i></div><div><label>Sağlık <em>2 record</em></label><i><b style={{width: '27%'}} /></i></div></div>
          <div className="gap-callout"><span>!</span><div><b>Fırsat alanı</b><small>Sağlık · EMEA için record eksik</small></div></div>
        </div>
      </section>

      <section className="query-section">
        <div><span className="eyebrow">QUERY</span><h2>En doğru record, en ilgili case study.</h2></div>
        <p>İhtiyacınızı query olarak yazın. Sistem, tanımlı sıralama ve benzerlik kriterlerine göre record havuzundaki en yakın eşleşmeyi seçer; ardından bu record üzerinden size özel bir case study üretir.</p>
        <Link className="primary-action" to="/query">Query ile başla <span>→</span></Link>
      </section>
    </main>
  );
}

function App() {
  return (
    <div className="app-container">
      <Sidebar />
      <div className="main-content">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/upload-record" element={<UploadRecord />} />
          <Route path="/engagments" element={<Engagments/>} />
          <Route path="/engagements" element={<Engagments/>} />
          <Route path="/engagements/:id" element={<EngagementDetail/>} />
          <Route path="/engagements/:id/edit" element={<EditEngagement/>} />
          <Route path="/query" element={<Query />} />
          <Route path="/analyze" element={<Analyze />} />

        </Routes>
      </div>
    </div>
  );
}

export default App;
