<div align="right">
  <a href="README.md"><img src="https://img.shields.io/badge/-English-545759?style=for-the-badge" alt="English"></a>
  <img src="https://img.shields.io/badge/-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-A31F34?style=for-the-badge" alt="简体中文">
  <a href="README_zh-TW.md"><img src="https://img.shields.io/badge/-%E7%B9%81%E9%AB%94%E4%B8%AD%E6%96%87-545759?style=for-the-badge" alt="繁體中文"></a>
</div>

<p align="center">
  <img width="92" src="blog/static/images/redefine-logo.webp" alt="Redefine 标志">
</p>

<h1 align="center">django-redefine-blog</h1>

<p align="center">一个基于 Redefine 的 Django 博客。</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%E2%80%933.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 至 3.14">
  <img src="https://img.shields.io/badge/Django-6.0-0C4B33?style=flat-square&logo=django&logoColor=white" alt="Django 6.0">
  <img src="https://img.shields.io/badge/license-GPL--3.0-A31F34?style=flat-square" alt="GPL-3.0">
</p>

这个项目把
[hexo-theme-redefine](https://github.com/EvanNotFound/hexo-theme-redefine)
的页面和前端交互搬到了 Django。文章、评论、菜单和站点设置都保存在数据库里，平时直接通过 Django Admin 维护。

它是一个可以独立运行的博客项目，不是装进现有 Hexo 站点的主题。

## 现在能做什么

- 首页、文章、归档、分类、标签，以及 Friends、Bookmarks、Essays、Masonry 等 Redefine 页面
- Markdown 与 Redefine 常用的提示块、折叠、标签页、按钮和代码块写法
- 草稿、定时发布、相关文章、RSS、Sitemap 和服务端搜索
- 自带评论系统：账号资料、显示名称、头像、回复、点赞、审核、徽章、表情、GIF 和图片上传
- 浅色/深色模式、Swup 无刷新切换和七种界面语言
- 本地默认 SQLite，部署时可换 PostgreSQL 或 MySQL

不想使用内置评论的话，也可以在后台切换到 Waline、Gitalk、Twikoo 或 Giscus。

## 本地运行

支持 Python 3.12 至 3.14。

```bash
python -m venv .venv
```

PowerShell 使用 `.venv\Scripts\Activate.ps1` 激活环境；Linux 和 macOS 使用
`source .venv/bin/activate`。接着执行：

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

博客地址是 `http://127.0.0.1:8000/`，后台地址是
`http://127.0.0.1:8000/admin/`。

新数据库不会自动写入演示内容，登录后台按自己的需要配置即可。如果想先看看完整的演示站，可以运行：

```bash
python manage.py create_demo
```

它会创建演示导航、Hello World 文章、分类、标签和评论预设。已有站点配置时不会覆盖现有内容。开发环境默认使用 SQLite，邮件会打印在终端里。

## 部署

公开站点不要使用 `runserver`。生产配置全部从环境变量读取，可用变量见
[.env.example](.env.example)。

[DEPLOYMENT.md](DEPLOYMENT.md) 里有 Gunicorn、systemd 和 Nginx 的部署步骤；Docker Compose、Redis、GitHub 登录等可选项放在
[OPTIONAL_FEATURES.md](OPTIONAL_FEATURES.md)。

## 测试

```bash
python manage.py check
python manage.py test blog
python manage.py makemigrations --check --dry-run
node --test tests/frontend-regressions.cjs
```

Node.js 只用于跑前端测试，网站本身不需要构建前端资源。

## 致谢与许可

前端基于 [EvanNotFound](https://github.com/EvanNotFound) 及其他贡献者开发的
[hexo-theme-redefine](https://github.com/EvanNotFound/hexo-theme-redefine)。本项目使用 GPL-3.0；仓库内第三方文件仍按各自许可分发，详情见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
