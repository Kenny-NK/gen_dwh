import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const resources = {
  ru: {
    translation: {
      nav_dashboard: "Панель",
      nav_sources: "Источники",
      nav_flows: "Потоки",
      nav_runs: "Запуски",
      nav_audit: "Аудит",
      nav_users_roles: "Пользователи и роли",
      nav_subtitle: "Управление потоками данных",
      action_logout: "Выйти",
      theme_light: "Светлая тема",
      theme_dark: "Темная тема",
      theme_toggle: "Тема интерфейса",
      notifications: "Уведомления",
      read_all: "Прочитать все",
      no_notifications: "Уведомлений нет",
      close: "Закрыть",
    },
  },
  en: {
    translation: {
      nav_dashboard: "Dashboard",
      nav_sources: "Sources",
      nav_flows: "Flows",
      nav_runs: "Runs",
      nav_audit: "Audit",
      nav_users_roles: "Users & roles",
      nav_subtitle: "Data pipeline management",
      action_logout: "Sign out",
      theme_light: "Light theme",
      theme_dark: "Dark theme",
      theme_toggle: "Interface theme",
      notifications: "Notifications",
      read_all: "Mark all as read",
      no_notifications: "No notifications",
      close: "Close",
    },
  },
};

void i18n.use(initReactI18next).init({
  resources,
  lng: "ru",
  fallbackLng: "ru",
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;
