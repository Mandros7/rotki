<script setup lang="ts">
import { Blockchain } from '@rotki/common';
import BlockchainAccountSelector from '@/components/helper/BlockchainAccountSelector.vue';
import TablePageLayout from '@/components/layout/TablePageLayout.vue';
import { useLidoCsmApi } from '@/composables/api/staking/lido-csm';
import type { AddressData, BlockchainAccount } from '@/types/blockchain/accounts';
import type { LidoCsmNodeOperator, LidoCsmNodeOperatorPayload } from '@/types/staking';
import { useMessageStore } from '@/store/message';
import { getAccountAddress } from '@/utils/blockchain/accounts/utils';

defineOptions({
  name: 'LidoCsmPage',
});

const { t } = useI18n({ useScope: 'global' });
const { isDark } = useRotkiTheme();

const nodeOperators = ref<LidoCsmNodeOperator[]>([]);
const loading = ref<boolean>(false);
const selectedAccount = ref<BlockchainAccount<AddressData>[]>([]);
const nodeOperatorId = ref<string>('');
const submitting = ref<boolean>(false);
const removingEntryKey = ref<string>('');
const dialogOpen = ref<boolean>(false);

const api = useLidoCsmApi();
const { setMessage } = useMessageStore();

const selectedAddress = computed<string>(() => {
  const account = get(selectedAccount)[0];
  return account ? getAccountAddress(account) : '';
});

const nodeOperatorInputError = computed<string | undefined>(() => {
  const value = get(nodeOperatorId).trim();
  if (value === '')
    return undefined;

  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0)
    return t('staking_page.lido_csm.form.validation.invalid_id');

  return undefined;
});

const nodeOperatorInputErrors = computed<string[]>(() => {
  const error = get(nodeOperatorInputError);
  return error ? [error] : [];
});

const formValid = computed<boolean>(() => {
  if (get(nodeOperatorInputError))
    return false;

  return get(selectedAddress) !== '' && get(nodeOperatorId).trim() !== '';
});

const notAvailableLabel = computed<string>(() => t('staking_page.lido_csm.table.not_available'));
const dialogDescription = computed<string>(() => t('staking_page.lido_csm.form.description'));
const stEthFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 6,
});

function toErrorMessage(error: unknown): string {
  if (error instanceof Error)
    return error.message;

  return String(error);
}

async function fetchNodeOperators(): Promise<void> {
  set(loading, true);
  try {
    set(nodeOperators, await api.listNodeOperators());
  }
  catch (error: unknown) {
    setMessage({
      description: t('staking_page.lido_csm.messages.fetch_failed', { message: toErrorMessage(error) }),
    });
  }
  finally {
    set(loading, false);
  }
}

async function refreshAllNodeOperators(): Promise<void> {
  set(loading, true);
  try {
    set(nodeOperators, await api.refreshMetrics());
  }
  catch (error: unknown) {
    setMessage({
      description: t('staking_page.lido_csm.messages.refresh_failed', { message: toErrorMessage(error) }),
    });
  }
  finally {
    set(loading, false);
  }
}

async function addNodeOperator(payload: LidoCsmNodeOperatorPayload): Promise<void> {
  try {
    set(nodeOperators, await api.addNodeOperator(payload));
  }
  catch (error: unknown) {
    setMessage({
      description: t('staking_page.lido_csm.messages.add_failed', { message: toErrorMessage(error) }),
    });
    throw error;
  }
}

async function deleteNodeOperator(payload: LidoCsmNodeOperatorPayload): Promise<void> {
  try {
    set(nodeOperators, await api.deleteNodeOperator(payload));
  }
  catch (error: unknown) {
    setMessage({
      description: t('staking_page.lido_csm.messages.delete_failed', { message: toErrorMessage(error) }),
    });
    throw error;
  }
}

function formatStEth(value?: string | null): string {
  if (!value)
    return get(notAvailableLabel);

  const numericValue = Number(value);
  const formatted = Number.isFinite(numericValue) ? stEthFormatter.format(numericValue) : value;
  return `${formatted} stETH`;
}

function formatCount(value?: number | null): string {
  if (value === undefined || value === null)
    return get(notAvailableLabel);

  return value.toString();
}

interface LidoCsmTableRow {
  key: string;
  address: string;
  nodeOperatorId: number;
  operatorTypeLabel: string;
  operatorTypeId: number | null;
  bondCurrent: string;
  bondRequired: string;
  bondClaimable: string;
  totalDeposited: string;
  rewardsPending: string;
}

const tableRows = computed<LidoCsmTableRow[]>(() => get(nodeOperators).map((entry) => {
  const metrics = entry.metrics;
  const operatorType = metrics?.operatorType;
  const bond = metrics?.bond;
  const keys = metrics?.keys;
  const rewards = metrics?.rewards;

  return {
    address: entry.address,
    bondClaimable: formatStEth(bond?.claimable ?? null),
    bondCurrent: formatStEth(bond?.current ?? null),
    bondRequired: formatStEth(bond?.required ?? null),
    key: `${entry.address}-${entry.nodeOperatorId}`,
    nodeOperatorId: entry.nodeOperatorId,
    operatorTypeId: operatorType?.id ?? null,
    operatorTypeLabel: operatorType?.label ?? get(notAvailableLabel),
    rewardsPending: formatStEth(rewards?.pending ?? null),
    totalDeposited: formatCount(keys?.totalDeposited ?? null),
  };
}));

const hasEntries = computed<boolean>(() => get(tableRows).length > 0);

function resetForm(): void {
  set(selectedAccount, []);
  set(nodeOperatorId, '');
}

function resetDialogState(): void {
  resetForm();
}

function closeDialog(): void {
  set(dialogOpen, false);
}

function openAddDialog(): void {
  resetDialogState();
  set(dialogOpen, true);
}

async function submitForm(): Promise<void> {
  if (!get(formValid) || get(submitting))
    return;

  set(submitting, true);
  try {
    await addNodeOperator({
      address: get(selectedAddress),
      nodeOperatorId: Number(get(nodeOperatorId)),
    });

    closeDialog();
  }
  finally {
    set(submitting, false);
  }
}

async function handleRemove(address: string, nodeOperatorIdValue: number): Promise<void> {
  const key = `${address}-${nodeOperatorIdValue}`;
  if (get(removingEntryKey) === key)
    return;

  set(removingEntryKey, key);
  try {
    await deleteNodeOperator({
      address,
      nodeOperatorId: nodeOperatorIdValue,
    });
  }
  finally {
    set(removingEntryKey, '');
  }
}

async function handleRefresh(): Promise<void> {
  if (get(loading))
    return;

  await refreshAllNodeOperators();
}

watch(dialogOpen, (isOpen) => {
  if (!isOpen)
    resetDialogState();
});

onMounted(async () => {
  if (get(nodeOperators).length === 0)
    await fetchNodeOperators();
});

defineExpose({
  refresh: handleRefresh,
});
</script>

<template>
  <TablePageLayout
    :title="[t('navigation_menu.staking'), t('staking_page.lido_csm.title')]"
    child
  >
    <template #buttons>
      <RuiButton
        color="primary"
        :disabled="loading"
        @click="openAddDialog()"
      >
        <template #prepend>
          <RuiIcon
            name="lu-plus"
            size="18"
          />
        </template>
        {{ t('staking_page.lido_csm.form.submit') }}
      </RuiButton>
      <RuiTooltip :open-delay="400">
        <template #activator>
          <RuiButton
            color="primary"
            variant="outlined"
            :loading="loading"
            @click="handleRefresh()"
          >
            <template #prepend>
              <RuiIcon name="lu-refresh-ccw" />
            </template>
            {{ t('common.refresh') }}
          </RuiButton>
        </template>
        {{ t('staking_page.lido_csm.table.refresh_tooltip') }}
      </RuiTooltip>
    </template>
    <div class="flex flex-col gap-6">
      <div>
        <p class="text-sm text-rui-text-secondary">
          {{ t('staking_page.lido_csm.description') }}
        </p>
      </div>

      <RuiCard>
        <div
          v-if="loading"
          class="space-y-3"
        >
          <RuiSkeletonLoader
            v-for="i in 3"
            :key="i"
            class="h-12"
          />
        </div>
        <div
          v-else-if="!hasEntries"
          class="flex flex-col items-center text-center text-rui-text-secondary py-8"
        >
          <img
            :src="isDark ? '/assets/images/placeholder/table_no_data_placeholder_dark.svg' : '/assets/images/placeholder/table_no_data_placeholder.svg'"
            :alt="t('staking_page.lido_csm.table.empty')"
            class="h-32"
          />
          {{ t('staking_page.lido_csm.table.empty') }}
        </div>
        <div
          v-else
          class="overflow-x-auto"
        >
          <p class="text-sm text-rui-text-secondary">
            {{ t('staking_page.lido_csm.table.description') }}
          </p>
          <table class="min-w-full text-left text-sm">
            <thead>
              <tr class="border-b border-rui-grey-200 dark:border-rui-grey-800 text-xs uppercase tracking-wide text-rui-text-secondary">
                <th class="py-3 pr-4">
                  {{ t('staking_page.lido_csm.table.address') }}
                </th>
                <th class="py-3 pr-4">
                  {{ t('staking_page.lido_csm.table.node_operator') }}
                </th>
                <th class="py-3 pr-4">
                  {{ t('staking_page.lido_csm.table.operator_type') }}
                </th>
                <th class="py-3 pr-4">
                  {{ t('staking_page.lido_csm.table.bond_current') }}
                </th>
                <th class="py-3 pr-4">
                  {{ t('staking_page.lido_csm.table.bond_required') }}
                </th>
                <th class="py-3 pr-4">
                  {{ t('staking_page.lido_csm.table.bond_claimable') }}
                </th>
                <th class="py-3 pr-4">
                  {{ t('staking_page.lido_csm.table.keys_total') }}
                </th>
                <th class="py-3 pr-4">
                  {{ t('staking_page.lido_csm.table.rewards_pending') }}
                </th>
                <th class="py-3 pr-3 text-right">
                  {{ t('staking_page.lido_csm.table.actions') }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in tableRows"
                :key="row.key"
                class="border-b border-rui-grey-100 dark:border-rui-grey-900 last:border-b-0"
              >
                <td class="py-3 pr-4 font-mono break-all text-sm">
                  {{ row.address }}
                </td>
                <td class="py-3 pr-4 text-sm">
                  {{ row.nodeOperatorId }}
                </td>
                <td class="py-3 pr-4 text-sm">
                  <div class="font-medium">
                    {{ row.operatorTypeLabel }}
                  </div>
                </td>
                <td class="py-3 pr-4 text-sm">
                  {{ row.bondCurrent }}
                </td>
                <td class="py-3 pr-4 text-sm">
                  {{ row.bondRequired }}
                </td>
                <td class="py-3 pr-4 text-sm">
                  {{ row.bondClaimable }}
                </td>
                <td class="py-3 pr-4 text-sm">
                  {{ row.totalDeposited }}
                </td>
                <td class="py-3 pr-4 text-sm">
                  {{ row.rewardsPending }}
                </td>
                <td class="py-2 pr-2">
                  <div class="flex justify-end gap-1">
                    <RuiButton
                      color="error"
                      variant="text"
                      size="sm"
                      :loading="removingEntryKey === row.key"
                      @click="handleRemove(row.address, row.nodeOperatorId)"
                    >
                      {{ t('staking_page.lido_csm.table.remove') }}
                    </RuiButton>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </RuiCard>

      <RuiDialog
        v-model="dialogOpen"
        max-width="520"
      >
        <RuiCard
          divide
          no-padding
          content-class="overflow-hidden"
        >
          <template #header>
            {{ t('staking_page.lido_csm.form.title') }}
          </template>
          <RuiButton
            variant="text"
            class="absolute top-2 right-2"
            icon
            @click="closeDialog()"
          >
            <RuiIcon
              class="text-white"
              name="lu-x"
            />
          </RuiButton>
          <div class="p-4 space-y-6">
            <p class="text-sm text-rui-text-secondary">
              {{ dialogDescription }}
            </p>
            <div class="grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <BlockchainAccountSelector
                v-model="selectedAccount"
                :chains="[Blockchain.ETH]"
                outlined
                :label="t('staking_page.lido_csm.form.address_label')"
                :custom-hint="t('staking_page.lido_csm.form.address_hint')"
              />
              <RuiTextField
                v-model="nodeOperatorId"
                type="number"
                min="0"
                step="1"
                color="primary"
                :label="t('staking_page.lido_csm.form.node_operator_label')"
                :hint="t('staking_page.lido_csm.form.node_operator_hint')"
                :error-messages="nodeOperatorInputErrors"
                variant="outlined"
              />
            </div>
          </div>
          <template #footer>
            <div class="w-full flex justify-end gap-2 pt-2">
              <RuiButton
                variant="text"
                @click="closeDialog()"
              >
                {{ t('common.actions.cancel') }}
              </RuiButton>
              <RuiButton
                color="primary"
                :loading="submitting"
                :disabled="!formValid"
                @click="submitForm()"
              >
                {{ t('staking_page.lido_csm.form.submit') }}
              </RuiButton>
            </div>
          </template>
        </RuiCard>
      </RuiDialog>
    </div>
  </TablePageLayout>
</template>
