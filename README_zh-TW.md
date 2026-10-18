<div align="right">
  <a href="README.md"><img src="https://img.shields.io/badge/-English-545759?style=for-the-badge" alt="English"></a>
  <a href="README_zh-CN.md"><img src="https://img.shields.io/badge/-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-545759?style=for-the-badge" alt="简体中文"></a>
  <img src="https://img.shields.io/badge/-%E7%B9%81%E9%AB%94%E4%B8%AD%E6%96%87-A31F34?style=for-the-badge" alt="繁體中文">
</div>

<p align="center">
  <img width="92" src="blog/static/images/redefine-logo.webp" alt="Redefine 標誌">
</p>

<h1 align="center">django-redefine-blog</h1>

<p align="center">
  一款以 Django 重寫 Redefine 主題的部落格
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%E2%80%933.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 至 3.14">
  <img src="https://img.shields.io/badge/Django-6.0-0C4B33?style=flat-square&logo=django&logoColor=white" alt="Django 6.0">
  <img src="https://img.shields.io/badge/license-GPL--3.0-A31F34?style=flat-square" alt="GPL-3.0">
</p>

這個專案是對 [hexo-theme-redefine](https://github.com/EvanNotFound/hexo-theme-redefine) 2.8.5 的移植。
範本、頁面配置、Markdown 元件等都搬到了 Django，並在此基礎上加入資料庫內容管理、留言、搜尋等功能。

## 現有功能

- Redefine 風格的首頁、文章、彙整、分類、標籤與獨立頁面，包含響應式配置
- 淺色/深色模式、Swup 頁面切換、本機搜尋、目錄、圖片檢視器與側邊工具
- 可在 Admin 介面管理的 Friends、Bookmarks、Essays 與 Masonry 頁面
- 相容 Redefine 2.8.5 常用的 Note、Folding、Tabs、Buttons 與程式碼區塊寫法
- 草稿、排程發佈、穩定連結、推薦文章、RSS 與 Sitemap
- 內建留言系統，支援登入/註冊帳號、審核、徽章、按讚、回覆、表情、GIF 與圖片上傳
- 可選的 Waline、Gitalk、Twikoo 與 Giscus 整合
- `export_blog` 與 `import_blog` 指令，方便搬移文章、帳號、設定和上傳檔案

## 本機執行

支援 Python 3.12 ~ Python 3.14。

```bash
python -m venv .venv
```

啟用虛擬環境：

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux 和 macOS
source .venv/bin/activate
```

安裝依賴並初始化資料庫：

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

開啟 `http://127.0.0.1:8000/admin/`，使用剛建立的超級使用者登入。第一次遷移會建立預設網站設定，之後可以在後台調整網站資訊、導覽、留言系統與主題選項。

開發環境預設使用 SQLite，郵件只會輸出到終端。正式環境的金鑰、網域和郵件連線全部從環境變數讀取，部署前請閱讀 [.env.example](.env.example) 和 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 測試

Django 測試涵蓋發佈規則、留言、Markdown、後台、RSS、備份與資料約束；前端測試直接執行瀏覽器模組即可。

```bash
python manage.py check
python manage.py test blog
python manage.py makemigrations --check --dry-run
node --test tests/frontend-regressions.cjs
```

Node.js 只用於前端測試，網站本身不需要前端建置。

## 內容與備份

上傳檔案保存在 `blog/resources/`，該目錄已從 Git 排除。需要搬移部落格時，請使用專案內建的封存指令，不要提交資料庫和媒體檔案：

```bash
python manage.py export_blog blog-backup.zip
python manage.py import_blog blog-backup.zip
```

備份包可能包含密碼雜湊、私人設定和上傳檔案，應按敏感資料保存。匯入和覆寫選項請見 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 一些說明

- 網站本身的設定放在 Django Admin 中，會改變專案整體結構的配置常數放在 `config/settings.py` 中。
- Site PV、Site UV 和文章 PV 已有資料支援，分別控制三者是否顯示的開關會在後續補充。

後台使用說明請見 [ADMIN_GUIDE.md](ADMIN_GUIDE.md)。

## 致謝與授權

前端基於 [EvanNotFound](https://github.com/EvanNotFound) 開發的 [hexo-theme-redefine](https://github.com/EvanNotFound/hexo-theme-redefine)。Redefine 使用 GPL-3.0，本專案與 hexo-theme-redefine 沿用同一授權。

倉庫內直接提供的第三方函式庫與字型仍受各自的著作權和授權條款約束，重新散布前請閱讀 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

完整專案授權請見 [LICENSE](LICENSE)。
