<div align="right">
  <a href="README.md"><img src="https://img.shields.io/badge/-English-545759?style=for-the-badge" alt="English"></a>
  <img src="https://img.shields.io/badge/-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-A31F34?style=for-the-badge" alt="简体中文">
  <a href="README_zh-TW.md"><img src="https://img.shields.io/badge/-%E7%B9%81%E9%AB%94%E4%B8%AD%E6%96%87-545759?style=for-the-badge" alt="繁體中文"></a>
</div>

<p align="center">
  <img width="92" src="blog/static/images/redefine-logo.webp" alt="Redefine 标志">
</p>

<h1 align="center">django-redefine-blog</h1>

<p align="center">
  一款用 Django 重写 Redefine 主题的博客
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%E2%80%933.14-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12 至 3.14">
  <img src="https://img.shields.io/badge/Django-6.0-0C4B33?style=flat-square&logo=django&logoColor=white" alt="Django 6.0">
  <img src="https://img.shields.io/badge/license-GPL--3.0-A31F34?style=flat-square" alt="GPL-3.0">
</p>

此项目是对 [hexo-theme-redefine](https://github.com/EvanNotFound/hexo-theme-redefine) 2.8.5 版本的移植。
模板、页面布局、Markdown 组件等都迁到了 Django，并在此基础上增加数据库内容管理、评论、搜索等。

## 已有功能

- Redefine 风格的首页、文章、归档、分类、标签和独立页面，包含响应式布局
- 浅色/深色模式、Swup 页面切换、本地搜索、目录、图片查看器和侧边工具
- 可在 Admin 界面管理的 Friends、Bookmarks、Essays 和 Masonry 页面
- 兼容 Redefine 2.8.5 常用的 Note、Folding、Tabs、Buttons 和代码块写法
- 草稿、定时发布、稳定链接、推荐文章、RSS 和 Sitemap
- 自带评论系统，支持登录/注册账号、审核、徽章、点赞、回复、表情、GIF 和图片上传
- 可选的 Waline、Gitalk、Twikoo 与 Giscus 接入
- `export_blog` 与 `import_blog` 命令，便于搬迁文章、账号、配置和上传文件

## 本地运行

支持 Python 3.12 ~ Python 3.14。

```bash
python -m venv .venv
```

激活虚拟环境：

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux 和 macOS
source .venv/bin/activate
```

安装依赖并初始化数据库：

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

打开 `http://127.0.0.1:8000/admin/`，使用刚创建的超级用户登录。第一次迁移会建立默认站点配置，之后可以在后台调整站点信息、导航、评论系统和主题选项。

开发环境默认使用 SQLite，邮件仅会输出到终端。生产环境的密钥、域名和邮箱连接全部从环境变量读取，
部署前请阅读 [.env.example](.env.example) 和 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 测试

Django 测试覆盖发布规则、评论、Markdown、后台、RSS、备份和数据约束，前端测试直接运行浏览器模块即可。

```bash
python manage.py check
python manage.py test blog
python manage.py makemigrations --check --dry-run
node --test tests/frontend-regressions.cjs
```

Node.js 仅用于前端测试，网站本身不需要前端构建。

## 内容与备份

上传文件保存在 `blog/resources/`，该目录已从 Git 中排除。需要迁移博客时，请使用项目自带的归档命令，不要提交数据库和媒体文件：

```bash
python manage.py export_blog blog-backup.zip
python manage.py import_blog blog-backup.zip
```

备份包可能包含密码哈希、私有配置和上传文件，应按敏感数据保存。导入和覆盖选项见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 一些说明

- 网站自身的配置放在 Django Admin中，会改变项目整体结构的布局常量放在 `config/settings.py`中。
- Site PV、Site UV 和文章 PV 已有数据支持，分别控制三者是否显示的开关将在后续补充。

后台使用说明见 [ADMIN_GUIDE.md](ADMIN_GUIDE.md)。

## 致谢与许可

前端基于 [EvanNotFound](https://github.com/EvanNotFound) 开发的 [hexo-theme-redefine](https://github.com/EvanNotFound/hexo-theme-redefine)。Redefine 使用 GPL-3.0，本项目与 hexo-theme-redefine 沿用同一许可证。

仓库内直接提供的第三方库和字体仍受各自的版权与许可约束，重新分发前请阅读 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

完整项目许可见 [LICENSE](LICENSE)。
