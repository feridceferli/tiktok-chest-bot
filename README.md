# TikTok Chest Bot

TikTok LIVE səhifələrini yoxlayır və sandıqla bağlı görünən mətn aşkarlandıqda Telegram qrupuna bildiriş göndərir.

## Render
Dockerfile Chromium və sistem asılılıqlarını build zamanı quraşdırır.
Render Environment bölməsində BOT_TOKEN və CHAT_ID saxlanılır; məxfi dəyərləri GitHub-a yazmayın.
SCAN_INTERVAL yoxlamalar arasındakı fasilədir (standart: 60 saniyə).
/health botun vəziyyətini göstərir; token və qrup ID-si göstərilmir.

Pulsuz Render xidməti 15 dəqiqə daxil olan trafik olmadıqda dayanır. Fasiləsiz iş üçün ödənişli xidmət lazımdır.
TikTok giriş və ya CAPTCHA tələb edərsə bot bunu keçmir.
Sandıq aşkarlanması görünən mətndə açar sözlərə əsaslanır; dəqiq TikTok sandıq API-si deyil.
Eyni istifadəçi üçün bildiriş 6 saat ərzində prosesin yaddaşında təkrarlanmır; restart bunu sıfırlayır.
Əvvəl açıq repoda paylaşılmış tokeni BotFather vasitəsilə yeniləyin.
