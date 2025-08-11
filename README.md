CRLChecker

Версия для ФНС 



    environment:
      - TZ=Europe/Moscow
      - TELEGRAM_BOT_TOKEN=
      - TELEGRAM_CHAT_ID=
      - FNS_ONLY=true

        # Уведомления TSL
      - NOTIFY_NEW_CAS=true
      - NOTIFY_DATE_CHANGES=true
      - NOTIFY_CRL_CHANGES=true
      - NOTIFY_STATUS_CHANGES=true
        
        # Уведомления CRL
      - NOTIFY_EXPIRING_CRL=true
      - NOTIFY_EXPIRED_CRL=true
      - NOTIFY_NEW_CRL=true
      - NOTIFY_MISSED_CRL=true
      - NOTIFY_WEEKLY_STATS=true


Версия для всех УЦ:


      - TZ=Europe/Moscow
      - TELEGRAM_BOT_TOKEN=
      - TELEGRAM_CHAT_ID=
      - FNS_ONLY=false

        # Уведомления TSL
      - NOTIFY_NEW_CAS=true
      - NOTIFY_DATE_CHANGES=true
      - NOTIFY_CRL_CHANGES=true
      - NOTIFY_STATUS_CHANGES=true
 
        # Уведомления CRL
      - NOTIFY_EXPIRING_CRL=true
      - NOTIFY_EXPIRED_CRL=false
      - NOTIFY_NEW_CRL=true
      - NOTIFY_MISSED_CRL=true
      - NOTIFY_WEEKLY_STATS=false

	Типы уведомлений и их сопоставления:

	1. Уведомления TSL (Удостоверяющие Центры)
	NOTIFY_NEW_CAS
	false/true
	Новые УЦ
	Уведомления о новых действующих УЦ в TSL
	NOTIFY_DATE_CHANGES
	false/true
	Изменения дат
	Уведомления об изменениях дат аккредитации УЦ
	NOTIFY_CRL_CHANGES
	false/true
	Изменения CRL
	Уведомления о новых или измененных CRL у действующих УЦ
	NOTIFY_STATUS_CHANGES
	false/true
	Изменения статуса
	Уведомления об изменении статуса УЦ

	2. Уведомления CRL (Списки Отозванных Сертификатов)
	NOTIFY_EXPIRING_CRL
	false/true
	Скоро истекает
	Уведомления об истекающих CRL (по пороговым значениям)
	NOTIFY_EXPIRED_CRL
	false/true
	Истекший
	Уведомления об истекших CRL
	NOTIFY_NEW_CRL
	false/true
	Новый CRL
	Уведомления о новых версиях CRL
	NOTIFY_MISSED_CRL
	false/true
	Пропущенный
	Уведомления о неопубликованных CRL
	NOTIFY_WEEKLY_STATS
	false/true
	Недельная статистика
	Уведомления о недельной статистике отозванных сертификатов
