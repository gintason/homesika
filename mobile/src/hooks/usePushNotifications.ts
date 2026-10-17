import { useQueryClient } from "@tanstack/react-query";
import * as Notifications from "expo-notifications";
import { router, type Href } from "expo-router";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { alertsApi } from "@/api";
import { configureNotifications, registerForPush, routeFor, type PushData } from "@/lib/push";

import { keys } from "./queries";

configureNotifications();

/** While signed in: register this phone for pushes, and react to alerts as they arrive or are tapped. */
export function usePushNotifications() {
  const { t } = useTranslation();
  const qc = useQueryClient();

  useEffect(() => {
    void registerForPush({ alerts: t("estate.alert.title"), updates: t("estate.news.title") });
    // registration is once per sign-in; the channel names don't need to follow language changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const seen = (data: PushData) => {
      if (data.type === "panic" && data.alert) alertsApi.received(data.alert).catch(() => {});
      if (data.type === "panic_status") void qc.invalidateQueries({ queryKey: keys.alerts });
      if (data.type === "announcement") void qc.invalidateQueries({ queryKey: keys.estates });
      if (data.type === "gate") void qc.invalidateQueries({ queryKey: keys.passes });
    };
    const received = Notifications.addNotificationReceivedListener((n) => seen((n.request.content.data ?? {}) as PushData));
    const tapped = Notifications.addNotificationResponseReceivedListener((r) => {
      const data = (r.notification.request.content.data ?? {}) as PushData;
      seen(data);
      const to = routeFor(data);
      if (to) router.push(to as Href);
    });
    return () => {
      received.remove();
      tapped.remove();
    };
  }, [qc]);
}
