from django.conf import settings

def site_assets(request):
    site = getattr(request, 'site', None)

    asset_config = {
        "cdn_enabled": False,
        "cdn_base": "",
        "swup_enabled": False,
    }

    if site and site.cdn_enabled:
        providers = {
            "npmmirror": "https://registry.npmmirror.com/hexo-theme-redefine/{version}/files/source/",
            "jsdelivr": "https://cdn.jsdelivr.net/npm/hexo-theme-redefine@{version}/source/",
            "zstatic": "https://s4.zstatic.net/ajax/libs/hexo-theme-redefine/{version}/",
            "cdnjs": "https://cdnjs.cloudflare.com/ajax/libs/hexo-theme-redefine/{version}/",
            "unpkg": "https://unpkg.com/hexo-theme-redefine@{version}/source/",
        }

        version = getattr(settings, "SITE_VERSION", "2.6.4")

        if site.cdn_provider == "custom" and site.cdn_custom_url:
            asset_config["cdn_base"] = site.cdn_custom_url.rstrip("/") + "/"
        else:
            base = providers.get(site.cdn_provider)
            if base:
                asset_config["cdn_base"] = base.format(version=version)

        asset_config["cdn_enabled"] = True

    asset_config["swup_enabled"] = bool(site and site.swup_enabled)

    return {
        "asset_config": asset_config
    }
