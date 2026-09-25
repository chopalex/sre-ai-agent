# Runbook: Nginx 502/504 Bad Gateway Troubleshooting (RB-OPS-103)

## Описание инцидента
Клиенты получают HTTP 502 Bad Gateway или HTTP 504 Gateway Timeout. Уровень 5xx ошибок в мониторинге превышает 1%.

## Шаги локализации
1. Проверить статус процесса веб-сервера Nginx:
   `systemctl status nginx`
2. Проверить последние критические ошибки в error_log:
   `tail -n 50 /var/log/nginx/error.log`
3. Проверить доступность upstream сокета/порта (например, uwsgi, gunicorn или php-fpm):
   `curl -sI -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/health`
4. Проверить лимиты открытых файловых дескрипторов процесса:
   `cat /proc/$(pgrep -o nginx)/limits | grep "Max open files"`

## Типовые причины и устранение
- **502 Connection refused:** upstream сервис упал. Проверить `systemctl status backend` и запустить при необходимости.
- **504 Gateway Timeout:** бэкенд перегружен медленными SQL-запросами или не справляется с очередью.
- **Too many open files:** исчерпан лимит `worker_rlimit_nofile` в `nginx.conf`.
