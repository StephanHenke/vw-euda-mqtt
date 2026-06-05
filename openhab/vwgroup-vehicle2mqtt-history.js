const { items, rules, time, triggers } = require('openhab');
const DecimalType = Java.type('org.openhab.core.library.types.DecimalType');
const OnOffType = Java.type('org.openhab.core.library.types.OnOffType');
const ZonedDateTime = Java.type('java.time.ZonedDateTime');

const HISTORY_BATCH_ITEM = 'Audi_History_Batch_JSON';
const PERSISTENCE_SERVICE = 'timescaledb';

const ITEM_BY_CURATED_TOPIC = {
  'battery/soc': 'Audi_Battery_SOC',
  'battery/target_soc': 'Audi_Target_SOC',
  'battery/charge_power_kw': 'Audi_Charge_Power',
  'odometer/km': 'Audi_Odometer',
  'range/km': 'Audi_Range',
  'charging/state': 'Audi_Charging_State',
  'doors/locked': 'Audi_Doors_Locked',
};

function stateForHistoryEvent(entry) {
  if (entry.value === null || entry.value === undefined) {
    return null;
  }
  if (typeof entry.value === 'boolean') {
    return entry.value ? OnOffType.ON : OnOffType.OFF;
  }
  if (typeof entry.value === 'number') {
    return new DecimalType(String(entry.value));
  }
  return String(entry.value);
}

function persistHistoryState(itemName, capturedAt, state) {
  const item = items.getItem(itemName);
  const timestamp = time.toZDT(ZonedDateTime.parse(capturedAt));
  if (PERSISTENCE_SERVICE) {
    item.persistence.persist(timestamp, state, PERSISTENCE_SERVICE);
    return;
  }
  item.persistence.persist(timestamp, state);
}

rules.JSRule({
  name: 'VW Group Vehicle2MQTT history backfill',
  description: 'Persists vehicle history batch events using their car_captured_at timestamp.',
  triggers: [triggers.ItemStateUpdateTrigger(HISTORY_BATCH_ITEM)],
  execute: () => {
    const state = items.getItem(HISTORY_BATCH_ITEM).state;
    const payload = state === undefined || state === null ? '' : state.toString();
    if (!payload || payload === 'NULL' || payload === 'UNDEF') {
      return;
    }

    let batch;
    try {
      batch = JSON.parse(payload);
    } catch (error) {
      console.warn(`VW Group Vehicle2MQTT history batch is not valid JSON: ${error}`);
      return;
    }

    const countsByItem = new Map();
    for (const entry of batch.events || []) {
      const itemName = ITEM_BY_CURATED_TOPIC[entry.curated_topic];
      if (!itemName || !entry.car_captured_at) {
        continue;
      }

      const state = stateForHistoryEvent(entry);
      if (state === null) {
        continue;
      }

      persistHistoryState(itemName, entry.car_captured_at, state);
      countsByItem.set(itemName, (countsByItem.get(itemName) || 0) + 1);
    }

    for (const [itemName, count] of countsByItem.entries()) {
      console.info(`VW Group Vehicle2MQTT persisted ${count} history values for ${itemName}`);
    }
  },
});
