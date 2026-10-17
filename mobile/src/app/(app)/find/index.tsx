import { Image } from "expo-image";
import { router } from "expo-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, View } from "react-native";

import type { ListingFilters, PublicListing } from "@/api";
import { Banner, Button, Card, EmptyState, MoneyText, Screen, SkeletonCard, Text, TextField } from "@/components";
import { useListings } from "@/hooks/queries";
import { errorText } from "@/lib/api";
import { formatMoney, parseAmountInput } from "@/lib/money";

const BEDROOMS = [null, 1, 2, 3, 4] as const;

/** Published listings anyone can see (GET /listings/), cheapest first, at most 30. */
export default function FindPlace() {
  const { t } = useTranslation();
  const [area, setArea] = useState("");
  const [maxRent, setMaxRent] = useState("");
  const [bedrooms, setBedrooms] = useState<number | null>(null);
  const [applied, setApplied] = useState<ListingFilters>({});
  const listings = useListings(applied);

  const rentError = maxRent.trim() && !parseAmountInput(maxRent) ? t("find.maxRentInvalid") : undefined;
  const search = () => {
    if (rentError) return;
    setApplied({ area: area.trim() || undefined, max_rent: parseAmountInput(maxRent) ?? undefined, bedrooms });
  };

  let results: React.ReactNode;
  if (listings.isPending && !listings.error) {
    results = (
      <View className="gap-4">
        <SkeletonCard label={t("common.loading")} />
        <SkeletonCard label={t("common.loading")} />
      </View>
    );
  } else if (!listings.data) {
    results = (
      <Banner message={`${t("errors.loadFailed")} ${errorText(listings.error)}`} onRetry={() => listings.refetch()} retryLabel={t("common.retry")} />
    );
  } else if (listings.data.length === 0) {
    results = <EmptyState icon="search-outline" title={t("find.empty")} body={t("find.emptyBody")} />;
  } else {
    results = (
      <View className="gap-4">
        {listings.error ? <Banner message={errorText(listings.error)} onRetry={() => listings.refetch()} retryLabel={t("common.retry")} /> : null}
        {listings.data.map((l) => (
          <ListingCard key={l.ref} listing={l} />
        ))}
      </View>
    );
  }

  return (
    <Screen title={t("find.title")} back onRefresh={() => listings.refetch()} refreshing={listings.isRefetching}>
      <Card>
        <TextField label={t("find.area")} hint={t("find.areaHint")} value={area} onChangeText={setArea} returnKeyType="search" onSubmitEditing={search} />
        <TextField
          label={t("find.maxRent")}
          hint={t("find.maxRentHint")}
          error={rentError}
          value={maxRent}
          onChangeText={setMaxRent}
          keyboardType="numeric"
          prefix="₦"
        />
        <Text variant="label">{t("find.bedrooms")}</Text>
        <View className="flex-row flex-wrap gap-2" accessibilityRole="radiogroup" accessibilityLabel={t("find.bedrooms")}>
          {BEDROOMS.map((n) => {
            const selected = bedrooms === n;
            const label = n === null ? t("find.any") : String(n);
            return (
              <Pressable
                key={label}
                onPress={() => setBedrooms(n)}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                accessibilityLabel={n === null ? t("find.anyBedrooms") : t("find.bedroomsCount", { n })}
                className={`min-h-12 min-w-12 items-center justify-center rounded-pill border-2 px-4 ${selected ? "border-primary-600 bg-primary-600" : "border-ink-400 bg-white"}`}
              >
                <Text variant="label" className={selected ? "text-white" : "text-ink-800"}>
                  {label}
                </Text>
              </Pressable>
            );
          })}
        </View>
        <Button title={t("find.search")} onPress={search} loading={listings.isFetching} />
      </Card>
      {results}
    </Screen>
  );
}

function ListingCard({ listing: l }: { listing: PublicListing }) {
  const { t } = useTranslation();
  const photo = l.photos[0];
  const period = l.rent_period === "month" ? t("find.perMonth") : t("find.perYear");
  const place = [l.area, l.city].filter(Boolean).join(", ");
  return (
    <Pressable
      onPress={() => router.push({ pathname: "/find/[ref]", params: { ref: l.ref } })}
      accessibilityRole="button"
      accessibilityLabel={t("find.cardLabel", { title: l.title, price: `${formatMoney(l.rent_amount, l.currency)} ${period}`, place })}
      className="overflow-hidden rounded-lg border border-surface-line bg-surface-card active:bg-surface-muted"
    >
      {photo ? (
        <Image
          source={{ uri: photo.url }}
          style={{ width: "100%", aspectRatio: 16 / 9 }}
          contentFit="cover"
          transition={0}
          cachePolicy="disk"
          accessible={false}
        />
      ) : null}
      <View className="gap-1 p-4">
        <Text variant="label">{l.title}</Text>
        <Text className="text-ink-600">{place}</Text>
        <View className="flex-row flex-wrap items-baseline gap-2">
          <MoneyText amount={l.rent_amount} currency={l.currency} />
          <Text variant="caption">{period}</Text>
        </View>
        {l.bedrooms ? <Text variant="caption">{t("find.bedroomsCount", { n: l.bedrooms })}</Text> : null}
      </View>
    </Pressable>
  );
}
