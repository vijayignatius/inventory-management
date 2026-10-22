<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <!-- Stats Grid -->
      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.stats.budget') }}</div>
          <div class="stat-value">{{ formatCurrency(budget, currentCurrency) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.stats.plannedSpend') }}</div>
          <div class="stat-value">{{ formatCurrency(plannedSpend, currentCurrency) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.stats.remaining') }}</div>
          <div class="stat-value">{{ formatCurrency(budget - plannedSpend, currentCurrency) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.stats.items') }}</div>
          <div class="stat-value">{{ selectedItems.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.stats.estLeadTime') }}</div>
          <div class="stat-value">{{ maxLeadTime }} {{ t('restocking.stats.days') }}</div>
        </div>
      </div>

      <!-- Budget Slider Card -->
      <div class="card budget-card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budget.title') }}</h3>
        </div>
        <div class="budget-control">
          <div class="budget-readout">
            <span class="budget-label">{{ t('restocking.budget.current') }}:</span>
            <span class="budget-amount">{{ formatCurrency(budget, currentCurrency) }}</span>
          </div>
          <input
            type="range"
            v-model.number="budget"
            :min="0"
            :max="maxBudget"
            :step="50"
            class="budget-slider"
            :aria-label="t('restocking.budget.current')"
            :aria-valuetext="formatCurrency(budget, currentCurrency)"
          />
          <div class="budget-limits">
            <span>{{ formatCurrency(0, currentCurrency) }}</span>
            <span>{{ formatCurrency(maxBudget, currentCurrency) }}</span>
          </div>
        </div>
      </div>

      <!-- Recommendations Table -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations.title') }}</h3>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.recommendations.table.sku') }}</th>
                <th>{{ t('restocking.recommendations.table.item') }}</th>
                <th>{{ t('restocking.recommendations.table.trend') }}</th>
                <th>{{ t('restocking.recommendations.table.gap') }}</th>
                <th>{{ t('restocking.recommendations.table.orderQty') }}</th>
                <th>{{ t('restocking.recommendations.table.unitCost') }}</th>
                <th>{{ t('restocking.recommendations.table.lineTotal') }}</th>
                <th>{{ t('restocking.recommendations.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="rec in recommendations"
                :key="rec.item_sku"
                :class="{ 'not-funded': rec.quantity === 0 }"
              >
                <td><strong>{{ rec.item_sku }}</strong></td>
                <td>{{ rec.item_name }}</td>
                <td>
                  <span :class="['badge', rec.trend]">
                    {{ t(`trends.${rec.trend}`) }}
                  </span>
                </td>
                <td>{{ rec.gap }}</td>
                <td>
                  <span v-if="rec.quantity > 0">
                    <strong>{{ rec.quantity }}</strong>
                    <span v-if="rec.isPartial" class="badge warning partial-badge">
                      {{ t('restocking.recommendations.partial') }}
                    </span>
                  </span>
                  <span v-else class="not-funded-text">
                    {{ t('restocking.recommendations.notFunded') }}
                  </span>
                </td>
                <td>{{ formatCurrency(rec.unit_cost, currentCurrency) }}</td>
                <td>
                  <strong v-if="rec.quantity > 0">
                    {{ formatCurrency(rec.lineTotal, currentCurrency) }}
                  </strong>
                  <span v-else>-</span>
                </td>
                <td>{{ rec.lead_time_days }} {{ t('restocking.stats.days') }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Place Order Button -->
        <div class="order-actions">
          <button
            class="place-order-btn"
            :disabled="selectedItems.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.order.submitting') : t('restocking.order.placeOrder') }}
          </button>
        </div>

        <!-- Error Display -->
        <div v-if="orderError" class="error">
          {{ orderError }}
        </div>

        <!-- Success Confirmation -->
        <div v-if="orderSuccess" class="success-panel">
          <div class="success-header">
            <h3>{{ t('restocking.order.success.title') }}</h3>
          </div>
          <div class="success-details">
            <p>
              <strong>{{ t('restocking.order.success.orderNumber') }}:</strong>
              {{ orderSuccess.order_number }}
            </p>
            <p>
              <strong>{{ t('restocking.order.success.expectedDelivery') }}:</strong>
              {{ formatDate(orderSuccess.expected_delivery) }}
            </p>
            <p>
              <strong>{{ t('restocking.order.success.leadTime') }}:</strong>
              {{ t('orders.leadTimeDays', { days: orderSuccess.lead_time_days }) }}
            </p>
            <p>
              <strong>{{ t('restocking.order.success.totalCost') }}:</strong>
              {{ formatCurrency(orderSuccess.total_cost, currentCurrency) }}
            </p>
          </div>
          <div class="success-actions">
            <router-link to="/orders" class="view-orders-link">
              {{ t('restocking.order.success.viewOrders') }}
            </router-link>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrencyWithDecimals } from '../utils/currency'
import { useFilters } from '../composables/useFilters'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale } = useI18n()
    const { selectedLocation, selectedCategory, getCurrentFilters } = useFilters()

    const loading = ref(true)
    const error = ref(null)
    const forecasts = ref([])
    const budget = ref(0)
    const submitting = ref(false)
    const orderError = ref(null)
    const orderSuccess = ref(null)

    // Show cents for USD: the shared formatCurrency rounds to whole dollars,
    // which would display unit costs like $6.40 as $6 and make line totals
    // disagree with what the server charges.
    const formatCurrency = (amount, currency) => {
      return formatCurrencyWithDecimals(amount, currency, 2)
    }

    // Calculate max budget: total cost of all recommendable items at full gap quantity, rounded up to next 100
    const maxBudget = computed(() => {
      const candidates = forecasts.value.filter(f => {
        const gap = f.forecasted_demand - f.current_demand
        return gap > 0
      })

      const totalCost = candidates.reduce((sum, item) => {
        const gap = item.forecasted_demand - item.current_demand
        return sum + (gap * item.unit_cost)
      }, 0)

      return Math.ceil(totalCost / 100) * 100
    })

    // Recommendation algorithm
    const recommendations = computed(() => {
      // Filter to candidates with positive gap
      const candidates = forecasts.value.filter(f => {
        const gap = f.forecasted_demand - f.current_demand
        return gap > 0
      })

      // Sort: trend 'increasing' first, then gap descending, then item_sku ascending
      const sorted = [...candidates].sort((a, b) => {
        const gapA = a.forecasted_demand - a.current_demand
        const gapB = b.forecasted_demand - b.current_demand

        // Trend priority: increasing > stable > decreasing
        const trendPriority = { increasing: 3, stable: 2, decreasing: 1 }
        if (trendPriority[a.trend] !== trendPriority[b.trend]) {
          return trendPriority[b.trend] - trendPriority[a.trend]
        }

        // Gap descending
        if (gapA !== gapB) {
          return gapB - gapA
        }

        // SKU ascending
        return a.item_sku.localeCompare(b.item_sku)
      })

      // Allocation: use integer cents to avoid floating point errors
      const budgetCents = Math.round(budget.value * 100)
      let remainingCents = budgetCents
      const result = []

      for (const item of sorted) {
        const gap = item.forecasted_demand - item.current_demand
        const unitCostCents = Math.round(item.unit_cost * 100)
        const fullCostCents = gap * unitCostCents

        let quantity = 0
        let isPartial = false

        if (fullCostCents <= remainingCents) {
          // Full funding
          quantity = gap
          remainingCents -= fullCostCents
        } else {
          // Partial funding: floor(remaining / unit_cost)
          quantity = Math.floor(remainingCents / unitCostCents)
          if (quantity >= 1) {
            isPartial = true
            remainingCents -= quantity * unitCostCents
          }
        }

        // Always include in result, even if quantity is 0
        result.push({
          item_sku: item.item_sku,
          item_name: item.item_name,
          trend: item.trend,
          gap,
          quantity,
          unit_cost: item.unit_cost,
          // Derive from cents, matching how the server computes line totals
          lineTotalCents: quantity * unitCostCents,
          lineTotal: (quantity * unitCostCents) / 100,
          lead_time_days: item.lead_time_days,
          isPartial
        })
      }

      return result
    })

    // Selected items (quantity > 0)
    const selectedItems = computed(() => {
      return recommendations.value.filter(r => r.quantity > 0)
    })

    // Planned spend
    const plannedSpend = computed(() => {
      return selectedItems.value.reduce((sum, item) => sum + item.lineTotalCents, 0) / 100
    })

    // Maximum lead time among selected items
    const maxLeadTime = computed(() => {
      if (selectedItems.value.length === 0) return 0
      return Math.max(...selectedItems.value.map(item => item.lead_time_days))
    })

    // Track whether this is the initial load
    const isInitialLoad = ref(true)

    // Load forecasts from API
    const loadForecasts = async () => {
      try {
        loading.value = true
        error.value = null
        const filters = getCurrentFilters()

        // Backend now filters forecasts by warehouse and category
        const data = await api.getDemandForecasts({
          warehouse: filters.warehouse,
          category: filters.category
        })
        forecasts.value = data

        // On initial load, set budget to half of max
        // On filter change, clamp budget to new max (don't reset)
        if (isInitialLoad.value) {
          const defaultBudget = Math.round((maxBudget.value / 2) / 50) * 50
          budget.value = defaultBudget
          isInitialLoad.value = false
        } else {
          // Clamp budget to new max when filters change
          if (budget.value > maxBudget.value) {
            budget.value = maxBudget.value
          }
        }
      } catch (err) {
        error.value = t('restocking.error.loadFailed')
        console.error('Failed to load forecasts:', err)
      } finally {
        loading.value = false
      }
    }

    // Watch Location and Category filters (Time Period and Order Status don't apply to forecasts)
    watch([selectedLocation, selectedCategory], () => {
      loadForecasts()
    })

    // Place order
    const placeOrder = async () => {
      if (selectedItems.value.length === 0) return

      try {
        submitting.value = true
        orderError.value = null
        orderSuccess.value = null

        const payload = {
          items: selectedItems.value.map(item => ({
            item_sku: item.item_sku,
            quantity: item.quantity
          })),
          budget: budget.value
        }

        const response = await api.createRestockingOrder(payload)
        orderSuccess.value = response
      } catch (err) {
        const detail = err.response?.data?.detail || t('restocking.error.orderFailed')
        orderError.value = detail
        console.error('Failed to create restocking order:', err)
      } finally {
        submitting.value = false
      }
    }

    // Format date for display
    const formatDate = (dateString) => {
      if (!dateString) return '-'
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return '-'

      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return date.toLocaleDateString(locale, {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      })
    }

    onMounted(loadForecasts)

    return {
      t,
      currentCurrency,
      loading,
      error,
      budget,
      maxBudget,
      recommendations,
      selectedItems,
      plannedSpend,
      maxLeadTime,
      submitting,
      orderError,
      orderSuccess,
      formatCurrency,
      formatDate,
      placeOrder
    }
  }
}
</script>

<style scoped>
/* Budget Card */
.budget-card {
  margin-bottom: 1.5rem;
}

.budget-control {
  padding: 1rem 0;
}

.budget-readout {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.budget-label {
  font-size: 0.938rem;
  color: #64748b;
  font-weight: 600;
}

.budget-amount {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

/* Budget Slider */
.budget-slider {
  width: 100%;
  height: 8px;
  border-radius: 4px;
  background: #e2e8f0;
  outline: none;
  -webkit-appearance: none;
  appearance: none;
  margin-bottom: 0.5rem;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  cursor: pointer;
  transition: all 0.2s ease;
}

.budget-slider::-webkit-slider-thumb:hover {
  background: #1e40af;
  transform: scale(1.1);
}

.budget-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  cursor: pointer;
  border: none;
  transition: all 0.2s ease;
}

.budget-slider::-moz-range-thumb:hover {
  background: #1e40af;
  transform: scale(1.1);
}

.budget-limits {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
}

/* Recommendations Table */
.not-funded {
  opacity: 0.5;
  background: #f8fafc;
}

.not-funded-text {
  color: #94a3b8;
  font-style: italic;
  font-size: 0.813rem;
}

.partial-badge {
  margin-left: 0.5rem;
  font-size: 0.688rem;
}

/* Order Actions */
.order-actions {
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
}

.place-order-btn {
  background: #2563eb;
  color: white;
  border: none;
  padding: 0.75rem 2rem;
  border-radius: 8px;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1e40af;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
  opacity: 0.6;
}

/* Success Panel */
.success-panel {
  margin-top: 1.5rem;
  padding: 1.5rem;
  background: #f0fdf4;
  border: 1px solid #86efac;
  border-radius: 8px;
}

.success-header h3 {
  color: #166534;
  font-size: 1.125rem;
  font-weight: 700;
  margin-bottom: 1rem;
}

.success-details {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.success-details p {
  color: #15803d;
  font-size: 0.938rem;
  margin: 0;
}

.success-actions {
  display: flex;
  justify-content: flex-end;
}

.view-orders-link {
  display: inline-block;
  padding: 0.625rem 1.5rem;
  background: #16a34a;
  color: white;
  text-decoration: none;
  border-radius: 6px;
  font-weight: 600;
  font-size: 0.875rem;
  transition: all 0.2s ease;
}

.view-orders-link:hover {
  background: #15803d;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(22, 163, 74, 0.3);
}
</style>
