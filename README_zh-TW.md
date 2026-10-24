<div align="right">
  <a href="README.md"><img src="https://img.shields.io/badge/-English-545759?style=for-the-badge" alt="English"></a>
  <a href="README_zh-CN.md"><img src="https://img.shields.io/badge/-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-545759?style=for-the-badge" alt="简体中文"></a>
  <img src="https://img.shields.io/badge/-%E7%B9%81%E9%AB%94%E4%B8%AD%E6%96%87-A31F34?style=for-the-badge" alt="繁體中文">
</div>

<p align="center">
  <img width="92" src="blog/static/images/redefine-logo.webp" alt="Redefine 標誌">
</p>

<h1 align="center">django-redefine-blog</h1>

<p align="center">一個基於 Redefine 的 Django 部落格。</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%E2%80%933.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 至 3.14">
  <img src="https://img.shields.io/badge/Django-6.0-0C4B33?style=flat-square&logo=django&logoColor=white" alt="Django 6.0">
  <img src="https://img.shields.io/badge/license-GPL--3.0-A31F34?style=flat-square" alt="GPL-3.0">
</p>

這個專案把
[hexo-theme-redefine](https://github.com/EvanNotFound/hexo-theme-redefine)
的版面與前端互動搬到 Django。文章、留言、選單和網站設定都存放在資料庫中，日常維護直接使用 Django Admin。

它是一個可以獨立執行的部落格專案，不是安裝到現有 Hexo 網站的主題。

## 目前包含

- 首頁、文章、彙整、分類、標籤，以及 Friends、Bookmarks、Essays、Masonry 等 Redefine 頁面
- Markdown 與 Redefine 常用的提示區塊、折疊、分頁、按鈕和程式碼區塊語法
- 草稿、排程發佈、相關文章、RSS、Sitemap 和伺服器端搜尋
- 內建留言系統：帳號、回覆、按讚、審核、徽章、表情、GIF 和圖片上傳
- 淺色/深色模式、Swup 無重新整理切換和七種介面語言
- 本機預設 SQLite，部署時可改用 PostgreSQL 或 MySQL

若不使用內建留言，也能在後台切換到 Waline、Gitalk、Twikoo 或 Giscus。

## 本機執行

支援 Python 3.12 至 3.14。

```bash
python -m venv .venv
```

PowerShell 使用 `.venv\Scripts\Activate.ps1` 啟用環境；Linux 和 macOS 使用
`source .venv/bin/activate`。接著執行：

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

部落格位於 `http://127.0.0.1:8000/`，管理後台位於
`http://127.0.0.1:8000/admin/`。

第一次遷移會建立一份預設網站設定和一篇起步文章，避免剛啟動時只看到空白頁；不需要時可直接在後台修改或刪除。開發環境預設使用 SQLite，郵件會輸出到終端機。

## 部署

公開網站不要使用 `runserver`。正式環境設定都從環境變數讀取，可用項目請見
[.env.example](.env.example)。

[DEPLOYMENT.md](DEPLOYMENT.md) 包含 Gunicorn、systemd 和 Nginx 的部署步驟；Docker Compose、Redis、GitHub 登入等選用功能放在
[OPTIONAL_FEATURES.md](OPTIONAL_FEATURES.md)。

## 測試

```bash
python manage.py check
python manage.py test blog
python manage.py makemigrations --check --dry-run
node --test tests/frontend-regressions.cjs
```

Node.js 只用於前端測試，網站本身不需要建置前端資源。

## 致謝與授權

前端基於 [EvanNotFound](https://github.com/EvanNotFound) 與其他貢獻者開發的
[hexo-theme-redefine](https://github.com/EvanNotFound/hexo-theme-redefine)。本專案使用 GPL-3.0；倉庫內的第三方檔案仍依各自授權散布，詳情請見
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
