    def send_tsl_removed_ca(self, ca_info):
        """Уведомление об удаленном УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"🗑️ <b>УЦ удален из списка</b>\n"
            f"🏢 Название: <b>{ca_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{ca_info['reg_number']}</code>\n"
            f"🏛️ ОГРН: <code>{ca_info.get('ogrn', 'Не указан')}</code>\n"
            f"📝 Причина: {ca_info['reason']}\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_name_change(self, change_info):
        """Уведомление об изменении названия УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"📝 <b>Изменение названия УЦ</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <b>{change_info['old_name']}</b>\n"
            f"📄 Стало: <b>{change_info['new_name']}</b>\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_ogrn_change(self, change_info):
        """Уведомление об изменении ОГРН УЦ"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"🏛️ <b>Изменение ОГРН УЦ</b>\n"
            f"🏢 Название: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было: <code>{change_info['old_ogrn']}</code>\n"
            f"📄 Стало: <code>{change_info['new_ogrn']}</code>\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_crl_added(self, change_info):
        """Уведомление о добавлении новых CRL"""
        if not NOTIFY_CRL_CHANGES:
            logger.debug("Уведомления об изменениях CRL отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        crl_list = "\n".join([f"• <code>{crl}</code>" for crl in change_info['crls']])
        message = (
            f"➕ <b>Добавлены новые CRL</b>\n"
            f"🏢 УЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📋 Новые CRL:\n{crl_list}\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_crl_removed(self, change_info):
        """Уведомление об удалении CRL"""
        if not NOTIFY_CRL_CHANGES:
            logger.debug("Уведомления об изменениях CRL отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        crl_list = "\n".join([f"• <code>{crl}</code>" for crl in change_info['crls']])
        message = (
            f"➖ <b>Удалены CRL</b>\n"
            f"🏢 УЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📋 Удаленные CRL:\n{crl_list}\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_crl_url_change(self, change_info):
        """Уведомление об изменении адресов CRL"""
        if not NOTIFY_CRL_CHANGES:
            logger.debug("Уведомления об изменениях CRL отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        old_urls = "\n".join([f"• <code>{url}</code>" for url in change_info['old_urls']])
        new_urls = "\n".join([f"• <code>{url}</code>" for url in change_info['new_urls']])
        message = (
            f"🔄 <b>Изменены адреса CRL</b>\n"
            f"🏢 УЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📄 Было:\n{old_urls}\n"
            f"📄 Стало:\n{new_urls}\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)

    def send_tsl_other_change(self, change_info):
        """Уведомление о других изменениях в TSL"""
        if not NOTIFY_STATUS_CHANGES:
            logger.debug("Уведомления об изменениях статуса УЦ отключены в конфигурации.")
            return
        now_msk = datetime.now(MOSCOW_TZ)
        message = (
            f"📋 <b>Другие изменения в TSL</b>\n"
            f"🏢 УЦ: <b>{change_info['name']}</b>\n"
            f"🔢 Реестровый номер: <code>{change_info['reg_number']}</code>\n"
            f"📝 Поле: <b>{change_info['field']}</b>\n"
            f"📄 Было: <code>{change_info['old_value']}</code>\n"
            f"📄 Стало: <code>{change_info['new_value']}</code>\n"
            f"🕐 Время проверки: {self.format_datetime(now_msk.isoformat())}"
        )
        self.send_message(message)
