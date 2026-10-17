import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, ScrollView, View } from "react-native";

import { listingFeatures, listingsApi, type PublicListingDetail } from "@/api";
import { Banner, Button, Card, MoneyText, PhoneInput, Screen, SkeletonCard, Text, TextField } from "@/components";
import { useListing } from "@/hooks/queries";
import { ApiError, errorText } from "@/lib/api";
import { formatDateTime } from "@/lib/date";
import { formatPhone, isValidPhone, normalisePhone } from "@/lib/phone";
import { useSession } from "@/store/session";
import tokens from "@/theme/tokens";

/** One listing: photos, price, features, open viewing times, "Book viewing" and "Ask about it". */
export default function ListingDetail() {
  const { t } = useTranslation();
  const { ref = "" } = useLocalSearchParams<{ ref: string }>();
  const listing = useListing(ref);

  let content: React.ReactNode;
  if (listing.isPending && !listing.error) {
    content = <SkeletonCard label={t("common.loading")} lines={5} />;
  } else if (!listing.data) {
    content = (
      <Banner message={`${t("errors.loadFailed")} ${errorText(listing.error)}`} onRetry={() => listing.refetch()} retryLabel={t("common.retry")} />
    );
  } else {
    content = <Details listing={listing.data} onSlotsChanged={() => listing.refetch()} />;
  }

  return (
    <Screen title={listing.data?.title ?? t("find.title")} back onRefresh={() => listing.refetch()} refreshing={listing.isRefetching}>
      {content}
    </Screen>
  );
}

function Details({ listing: l, onSlotsChanged }: { listing: PublicListingDetail; onSlotsChanged: () => void }) {
  const { t } = useTranslation();
  const profile = useSession((s) => s.profile);
  const [name, setName] = useState(`${profile?.firstName ?? ""} ${profile?.lastName ?? ""}`.trim());
  const [phone, setPhone] = useState((profile?.phone ?? "").replace(/^\+234/, ""));
  const [slot, setSlot] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<null | "book" | "ask">(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [phoneError, setPhoneError] = useState<string | null>(null);

  const features = listingFeatures(l.features);
  const period = l.rent_period === "month" ? t("find.perMonth") : t("find.perYear");
  const place = [l.area, l.city].filter(Boolean).join(", ");

  const contact = () => {
    const e164 = normalisePhone(phone);
    if (!isValidPhone(e164)) {
      setPhoneError(t("auth.phoneInvalid"));
      return null;
    }
    setPhoneError(null);
    return { name: name.trim(), phone_number: e164 };
  };

  const book = async () => {
    const who = contact();
    if (!who || !slot || busy) return;
    setBusy("book");
    setError(null);
    setDone(null);
    try {
      const res = await listingsApi.book(l.ref, { ...who, slot });
      setDone(t("find.booked", { time: formatDateTime(res.starts_at) }));
      setSlot(null);
      onSlotsChanged();
    } catch (e) {
      setError(errorText(e));
      if (e instanceof ApiError && e.code === "slot_unavailable") {
        setSlot(null);
        onSlotsChanged(); // show what's still open
      }
    } finally {
      setBusy(null);
    }
  };

  const ask = async () => {
    const who = contact();
    if (!who || busy) return;
    setBusy("ask");
    setError(null);
    setDone(null);
    try {
      await listingsApi.enquire(l.ref, message.trim() ? { ...who, message: message.trim() } : who);
      setDone(t("find.asked", { phone: formatPhone(who.phone_number) }));
      setMessage("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <View className="gap-5">
      {l.photos.length ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 12 }}>
          {l.photos.map((p, i) => (
            <Image
              key={p.id}
              source={{ uri: p.url }}
              style={{ width: 280, height: 190, borderRadius: tokens.radius.lg }}
              contentFit="cover"
              transition={0}
              cachePolicy="disk"
              accessible
              accessibilityLabel={p.caption || t("find.photo", { n: i + 1, total: l.photos.length })}
            />
          ))}
        </ScrollView>
      ) : null}

      <Card>
        <Text variant="heading" accessibilityRole="header">
          {l.title}
        </Text>
        <Text className="text-ink-600">{place}</Text>
        <View className="flex-row flex-wrap items-baseline gap-2">
          <MoneyText amount={l.rent_amount} currency={l.currency} variant="title" />
          <Text variant="caption">{period}</Text>
        </View>
        {l.bedrooms ? <Text>{t("find.bedroomsCount", { n: l.bedrooms })}</Text> : null}
        {l.bathrooms ? <Text>{t("find.bathroomsCount", { n: l.bathrooms })}</Text> : null}
        <Text variant="caption">{t("find.listedBy", { name: l.landlord })}</Text>
      </Card>

      {features.length ? (
        <Card>
          <Text variant="label" accessibilityRole="header">
            {t("find.features")}
          </Text>
          {features.map((f) => (
            <View key={f} className="flex-row items-start gap-2">
              <Ionicons name="checkmark" size={20} color={tokens.color.success[700]} />
              <Text className="flex-1">{f}</Text>
            </View>
          ))}
        </Card>
      ) : null}

      {l.description ? (
        <Card>
          <Text variant="label" accessibilityRole="header">
            {t("find.about")}
          </Text>
          <Text>{l.description}</Text>
        </Card>
      ) : null}

      <Card>
        <Text variant="label" accessibilityRole="header">
          {t("find.viewTimes")}
        </Text>
        {l.slots.length === 0 ? (
          <Text className="text-ink-600">{t("find.noSlots")}</Text>
        ) : (
          <View className="gap-2" accessibilityRole="radiogroup">
            {l.slots.map((s) => {
              const selected = slot === s.id;
              return (
                <Pressable
                  key={s.id}
                  onPress={() => setSlot(s.id)}
                  accessibilityRole="radio"
                  accessibilityState={{ selected }}
                  accessibilityLabel={formatDateTime(s.starts_at)}
                  className={`min-h-12 flex-row items-center gap-3 rounded-md border-2 px-4 py-2 ${selected ? "border-primary-600 bg-primary-50" : "border-ink-400 bg-white"}`}
                >
                  <Ionicons
                    name={selected ? "radio-button-on" : "radio-button-off"}
                    size={22}
                    color={selected ? tokens.color.primary[600] : tokens.color.ink[500]}
                  />
                  <Text variant="label">{formatDateTime(s.starts_at)}</Text>
                </Pressable>
              );
            })}
          </View>
        )}
      </Card>

      <Card>
        <Text variant="label" accessibilityRole="header">
          {t("find.yourDetails")}
        </Text>
        <TextField label={t("find.name")} value={name} onChangeText={setName} autoComplete="name" textContentType="name" />
        <PhoneInput label={t("find.phone")} value={phone} onChangeText={setPhone} error={phoneError ?? undefined} />
      </Card>

      {error ? <Banner message={error} /> : null}
      {done ? <Banner tone="success" message={done} /> : null}

      {l.slots.length ? (
        <Button
          title={t("find.book")}
          loading={busy === "book"}
          loadingLabel={t("find.booking")}
          disabled={!slot || !name.trim() || !phone.trim() || (busy !== null && busy !== "book")}
          accessibilityHint={slot ? undefined : t("find.pickSlot")}
          onPress={book}
        />
      ) : null}

      <Card>
        <TextField
          label={t("find.askMessage")}
          hint={t("common.optional")}
          value={message}
          onChangeText={setMessage}
          multiline
          maxLength={1000}
        />
        <Button
          title={t("find.ask")}
          variant="secondary"
          loading={busy === "ask"}
          disabled={!name.trim() || !phone.trim() || (busy !== null && busy !== "ask")}
          onPress={ask}
        />
      </Card>
    </View>
  );
}
