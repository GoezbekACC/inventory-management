<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div class="card budget-card">
      <label class="budget-label" for="budget-slider">
        {{ t('restocking.budget') }}: <strong>{{ money(budget) }}</strong>
      </label>
      <input
        id="budget-slider"
        v-model.number="budget"
        class="budget-slider"
        type="range"
        min="0"
        max="100000"
        step="1000"
      />
    </div>

    <div class="stats-grid">
      <div class="stat-card info">
        <div class="stat-label">{{ t('restocking.budget') }}</div>
        <div class="stat-value">{{ money(budget) }}</div>
      </div>
      <div class="stat-card warning">
        <div class="stat-label">{{ t('restocking.plannedSpend') }}</div>
        <div class="stat-value">{{ money(totalCost) }}</div>
      </div>
      <div class="stat-card success">
        <div class="stat-label">{{ t('restocking.remaining') }}</div>
        <div class="stat-value">{{ money(remaining) }}</div>
      </div>
    </div>

    <div v-if="loading && !loaded" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else class="card">
      <div class="card-header">
        <h3 class="card-title">{{ t('restocking.recommendations') }} ({{ items.length }})</h3>
        <button
          type="button"
          class="place-order-btn"
          :disabled="items.length === 0 || submitting || loading"
          @click="placeOrder"
        >
          {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
        </button>
      </div>

      <div v-if="orderError" class="inline-error">{{ orderError }}</div>
      <div v-if="placedOrder" class="inline-success">
        {{ t('restocking.orderPlaced', { orderNumber: placedOrder.order_number }) }}
        <router-link to="/orders">{{ t('restocking.viewOrders') }}</router-link>
      </div>

      <div v-if="items.length === 0" class="empty-state">{{ t('restocking.empty') }}</div>
      <div v-else class="table-container">
        <table>
          <thead>
            <tr>
              <th>{{ t('restocking.table.sku') }}</th>
              <th>{{ t('restocking.table.itemName') }}</th>
              <th>{{ t('restocking.table.trend') }}</th>
              <th>{{ t('restocking.table.quantity') }}</th>
              <th>{{ t('restocking.table.unitCost') }}</th>
              <th>{{ t('restocking.table.lineTotal') }}</th>
              <th>{{ t('restocking.table.leadTime') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in items" :key="item.item_sku">
              <td><strong>{{ item.item_sku }}</strong></td>
              <td>{{ translateProductName(item.item_name) }}</td>
              <td>
                <span :class="['badge', trendClass(item.trend)]">
                  {{ trendLabel(item.trend) }}
                </span>
              </td>
              <td>{{ item.quantity.toLocaleString() }}</td>
              <td>{{ money(item.unit_cost, 2) }}</td>
              <td><strong>{{ money(item.line_total) }}</strong></td>
              <td>{{ t('restocking.days', { count: item.lead_time_days }) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrencyWithDecimals } from '../utils/currency'

const { t, currentCurrency, translateProductName } = useI18n()

const budget = ref(50000)
const items = ref([])
const totalCost = ref(0)
const loading = ref(true)
const loaded = ref(false)
const error = ref(null)

const submitting = ref(false)
const orderError = ref(null)
const placedOrder = ref(null)

// Amounts from the API are in USD; formatter converts for the active currency.
const money = (amount, decimals = 0) =>
  formatCurrencyWithDecimals(Number(amount) || 0, currentCurrency.value, decimals)

const remaining = computed(() => Math.max(budget.value - totalCost.value, 0))

const trendClass = (trend) =>
  ({ increasing: 'success', stable: 'info', decreasing: 'warning' }[trend] || 'info')

const trendLabel = (trend) => (['increasing', 'stable', 'decreasing'].includes(trend) ? t(`trends.${trend}`) : trend)

let debounceTimer = null
let requestId = 0

const loadRecommendations = async () => {
  const myId = ++requestId
  loading.value = true
  error.value = null
  try {
    const data = await api.getRestockRecommendations(budget.value)
    if (myId !== requestId) return // stale response, a newer request is in flight
    items.value = data.items || []
    totalCost.value = data.total_cost || 0
    loaded.value = true
  } catch (err) {
    if (myId !== requestId) return
    console.error('Load error:', err)
    error.value = t('restocking.loadError')
  } finally {
    if (myId === requestId) loading.value = false
  }
}

// Debounce slider changes so dragging doesn't fire a request per step.
watch(budget, () => {
  placedOrder.value = null
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(loadRecommendations, 300)
})

const placeOrder = async () => {
  if (items.value.length === 0 || submitting.value) return
  submitting.value = true
  orderError.value = null
  placedOrder.value = null
  try {
    placedOrder.value = await api.createRestockOrder({
      items: items.value.map(i => ({ item_sku: i.item_sku, quantity: i.quantity })),
      budget: budget.value
    })
  } catch (err) {
    console.error('Order error:', err)
    orderError.value = t('restocking.orderError')
  } finally {
    submitting.value = false
  }
}

onMounted(loadRecommendations)
onBeforeUnmount(() => {
  clearTimeout(debounceTimer)
  requestId++ // invalidate any in-flight request
})
</script>

<style scoped>
.budget-card {
  padding: 1rem 1.5rem;
  margin-bottom: 1.5rem;
}

.budget-label {
  display: block;
  margin-bottom: 0.75rem;
  color: #64748b;
  font-size: 0.875rem;
}

.budget-label strong {
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  accent-color: #3b82f6;
}

.place-order-btn {
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
}

.place-order-btn:hover:not(:disabled) {
  background: #2563eb;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.inline-error,
.inline-success {
  margin: 0 1.5rem 1rem;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
}

.inline-error {
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
}

.inline-success {
  background: #f0fdf4;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.inline-success a {
  margin-left: 0.5rem;
  color: #2563eb;
  font-weight: 500;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}
</style>
