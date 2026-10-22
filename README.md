# TikTok Chest Bot

Kəşf edilən TikTok LIVE otaqlarına qoşulub real EnvelopeEvent hadisələrini Telegram qrupuna göndərir. Səhifədəki təsadüfi chest/treasure sözləri bildiriş yaratmır.

## Render dəyişənləri
- BOT_TOKEN və CHAT_ID: məxfi dəyərlər yalnız Render Environment bölməsində saxlanılır.
- MAX_ROOMS: eyni anda qoşulma sayı, standart 3 (maksimum 8).
- MONITOR_SECONDS: hər otaq üçün izləmə müddəti, standart 180 saniyə.
- TIKTOK_USERNAMES: əlavə izlənəcək istifadəçi adları, vergüllə ayrılır.
- /health: kəşf, qoşulmuş otaq və bildiriş sayları; məxfi dəyərləri göstərmir.

## Əhatə məhdudiyyəti
Bu bot bütün TikTok yayımlarını görə bilmir. TikTok LIVE kəşf səhifəsində görünən otaqları növbə ilə izləyir. Kəşfdən kənar yayımlar və botun qoşulmadığı vaxt yaranan hadisələr buraxıla bilər.
TikTokLive qeyri-rəsmi kitabxanadır və üçüncü tərəf imzalama serverindən istifadə edir; bağlantı və sorğu limitləri mövcuddur. Giriş/CAPTCHA maneələrini keçmir.
Pulsuz Render xidməti 15 dəqiqə daxil olan trafik olmadıqda dayanır. 24/7 iş üçün ödənişli xidmət tələb olunur.
Təkrar bildirişin qarşısı sandıq ID-si üzrə prosesin yaddaşında alınır; restart yaddaşı sıfırlayır.
\n512 MB yaddaş limiti üçün brauzer çıxarılıb. Kəşf yalnız açıq HTML-də təqdim edilən LIVE linklərindən adları oxuyur. TikTok bu siyahını açıq təqdim etmirsə TIKTOK_USERNAMES dəyişəninə izlənəcək hesablar əlavə edilməlidir.\n