<template>
  <section class="page" data-module="apigen">
    <header class="page-head">
      <div>
        <h2>API接口生成管理</h2>
        <p class="page-desc">维护API接口的方法定义、参数配置与响应模板，为API接口生成提供可验证的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记接口配置</button>
        <button class="btn" type="button" @click="exportRows">导出API接口生成清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form v-if="showForm" class="filter-bar entry-form" @submit.prevent="submitForm">
      <label v-for="field in formFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="form[field]" :placeholder="`请输入${field}`" />
      </label>
      <button class="btn primary" type="submit">保存接口配置</button>
      <button class="btn ghost" type="button" @click="closeForm">取消</button>
    </form>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <button v-if="column === '接口编号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无API接口生成数据，可先登记接口配置</td>
        </tr>
      </tbody>
    </table>

    <section v-if="detail" class="detail-panel">
      <header class="detail-head">
        <h3>接口配置详情：{{ detail['接口编号'] }}</h3>
        <button class="btn ghost" type="button" @click="closeDetail">收起详情</button>
      </header>
      <table class="data-table">
        <tbody>
          <tr v-for="column in columns" :key="column">
            <th>{{ column }}</th>
            <td>{{ detail[column] ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
      <template v-if="contract">
        <h4>请求参数（{{ contractParams.length }} 个）</h4>
        <table class="data-table">
          <thead>
            <tr><th>参数名</th><th>是否必填</th></tr>
          </thead>
          <tbody>
            <tr v-for="param in contractParams" :key="param.参数名">
              <td>{{ param.参数名 }}</td>
              <td>{{ param.是否必填 ? '必填' : '可选' }}</td>
            </tr>
            <tr v-if="!contractParams.length">
              <td colspan="2" class="empty-state">该接口尚未登记参数定义</td>
            </tr>
          </tbody>
        </table>
        <h4>错误码结构</h4>
        <pre class="contract-preview">{{ contractErrorText }}</pre>
      </template>
    </section>

    <section class="detail-panel">
      <header class="detail-head">
        <h3>请求响应契约清单</h3>
        <button class="btn ghost" type="button" @click="loadContracts">刷新契约清单</button>
      </header>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in contractColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in contracts" :key="`${item['接口编号']}-${item['版本']}`">
            <td v-for="column in contractColumns" :key="column">{{ item[column] ?? '—' }}</td>
          </tr>
          <tr v-if="!contracts.length">
            <td :colspan="contractColumns.length" class="empty-state">暂无已发布的请求响应契约</td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条API接口生成记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type ContractParam = { 参数名: string; 是否必填: boolean }

const ENDPOINT = '/api/apigen'
const columns = ["接口编号", "接口名称", "请求方法", "请求路径", "参数定义", "响应模板", "超时秒数", "接口状态", "版本"]
const actions = ["发布接口", "废弃接口", "删除接口"]
const statuses = ["草稿", "测试中", "已发布", "已废弃"]
const stats = [{"label": "接口配置总数", "value": 0}, {"label": "已发布接口", "value": 0}, {"label": "已废弃接口", "value": 0}]
const formFields = ["接口编号", "接口名称", "请求方法", "请求路径", "参数定义", "响应模板", "超时秒数"]
const contractColumns = ["接口编号", "接口名称", "版本", "请求方法", "请求路径", "超时秒数", "接口状态"]

const rows = ref<Row[]>([])
const contracts = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const showForm = ref(false)
const form = ref<Record<string, string>>({})
const detail = ref<Row | null>(null)
const contract = ref<Row | null>(null)

const contractParams = computed<ContractParam[]>(() => {
  const params = contract.value?.['请求参数']
  return Array.isArray(params) ? (params as ContractParam[]) : []
})

const contractErrorText = computed(() => {
  const error = contract.value?.['错误码结构']
  if (error === null || error === undefined) return '—'
  return typeof error === 'string' ? error : JSON.stringify(error, null, 2)
})

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  form.value = {}
  showForm.value = true
  errorMessage.value = ''
  noticeMessage.value = ''
}

function closeForm() {
  showForm.value = false
}

async function submitForm() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...form.value } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? payload.detail ?? '接口配置保存未生效，请稍后重试')
    }
    noticeMessage.value = payload.message ?? '接口配置已保存'
    showForm.value = false
    await reload()
    await loadContracts()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '接口配置保存失败'
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const [entryResp, contractResp] = await Promise.all([
      request(`${ENDPOINT}/${row.id}`),
      request(`${ENDPOINT}/${row.id}/contract`),
    ])
    if (!entryResp.ok) {
      throw new Error('接口配置明细读取失败')
    }
    detail.value = await entryResp.json()
    contract.value = contractResp.ok ? await contractResp.json() : null
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '接口配置明细读取失败'
  }
}

function closeDetail() {
  detail.value = null
  contract.value = null
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? 'API接口生成动作未生效，请稍后重试')
    }
    noticeMessage.value = payload.message ?? `接口配置已${action}`
    await reload()
    await loadContracts()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'API接口生成操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('接口配置列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'API接口生成列表读取失败'
  }
}

async function loadContracts() {
  try {
    const response = await request(`${ENDPOINT}/contracts`)
    if (!response.ok) {
      throw new Error('请求响应契约清单读取失败')
    }
    const payload = await response.json()
    contracts.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '请求响应契约清单读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadContracts()
})
</script>

<style scoped>
.detail-panel {
  margin-top: 16px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}
.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.detail-head h3 {
  margin: 0;
  font-size: 14px;
}
.detail-panel h4 {
  margin: 12px 0 6px;
  font-size: 13px;
}
.contract-preview {
  background: #f6f8fb;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 12px;
  white-space: pre-wrap;
}
.entry-form {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.notice-text {
  color: #067647;
}
</style>
