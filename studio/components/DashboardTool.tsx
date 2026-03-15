import React, {useEffect, useState, useCallback} from 'react'
import {useClient, useCurrentUser} from 'sanity'
import {useRouter} from 'sanity/router'
import {
  Box,
  Card,
  Flex,
  Grid,
  Heading,
  Stack,
  Text,
  Button,
  Spinner,
} from '@sanity/ui'
import {
  AddIcon,
  EditIcon,
  DocumentIcon,
  CogIcon,
  CheckmarkCircleIcon,
  CloseCircleIcon,
} from '@sanity/icons'
import styled from 'styled-components'

/* ────────────────────────────────────────────
   Types
   ──────────────────────────────────────────── */

interface Stats {
  systemNotes: number
  backupLogs: number
  systemProfiles: number
}

interface LatestBackup {
  status: string
  ranAt: string
  modules: string[]
}

interface RecentDoc {
  _id: string
  _type: string
  _updatedAt: string
  title?: string
  hostname?: string
  status?: string
  ranAt?: string
  category?: string
  device?: string
  siteTitle?: string
}

/* ────────────────────────────────────────────
   GROQ Queries
   ──────────────────────────────────────────── */

const STATS_QUERY = `{
  "systemNotes": count(*[_type == "systemNote"]),
  "backupLogs": count(*[_type == "backupLog"]),
  "systemProfiles": count(*[_type == "systemProfile"]),
  "latestBackup": *[_type == "backupLog"] | order(ranAt desc)[0] {
    status, ranAt, modules
  }
}`

const RECENT_QUERY = `*[_type in ["systemNote", "backupLog", "systemProfile", "siteContent"]] | order(_updatedAt desc)[0...7] {
  _id, _type, _updatedAt,
  title, hostname, status, ranAt, category, device,
  "siteTitle": site.title
}`

/* ────────────────────────────────────────────
   Constants
   ──────────────────────────────────────────── */

const TYPE_META: Record<string, {label: string; color: string}> = {
  systemNote: {label: 'System Note', color: '#4ecdc4'},
  backupLog: {label: 'Backup Log', color: '#ff6b6b'},
  systemProfile: {label: 'System Profile', color: '#a78bfa'},
  siteContent: {label: 'Site Content', color: '#fbbf24'},
}

/* ────────────────────────────────────────────
   Styled Components
   ──────────────────────────────────────────── */

const Wrapper = styled(Box)`
  max-width: 1440px;
  margin: 0 auto;
  padding: 1.5rem 2rem 3rem;
  overflow-y: auto;
  height: 100%;
`

const WelcomeCard = styled.div`
  background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #312e81 100%);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 12px;
  padding: 2rem;
`

const StatCard = styled.div<{$accent: string}>`
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-left: 3px solid ${(p) => p.$accent};
  border-radius: 8px;
  padding: 1rem 1.5rem;
  text-align: center;
  min-width: 140px;
  flex: 1;
`

const StatLabel = styled.div`
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: #94a3b8;
  margin-bottom: 0.25rem;
  text-transform: uppercase;
`

const StatValue = styled.div`
  font-size: 28px;
  font-weight: 700;
  color: #e2e8f0;
`

const StatSub = styled.div`
  font-size: 11px;
  color: #64748b;
`

const StatusCallout = styled.div<{$status?: string}>`
  background: ${(p) =>
    p.$status === 'success'
      ? 'linear-gradient(135deg, #064e3b, #065f46)'
      : p.$status === 'partial'
        ? 'linear-gradient(135deg, #78350f, #92400e)'
        : p.$status === 'failed'
          ? 'linear-gradient(135deg, #7f1d1d, #991b1b)'
          : 'linear-gradient(135deg, #1e293b, #334155)'};
  border: 1px solid
    ${(p) =>
      p.$status === 'success'
        ? 'rgba(52, 211, 153, 0.3)'
        : p.$status === 'partial'
          ? 'rgba(251, 191, 36, 0.3)'
          : p.$status === 'failed'
            ? 'rgba(248, 113, 113, 0.3)'
            : 'rgba(148, 163, 184, 0.2)'};
  border-radius: 12px;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 260px;
  flex: 1;
`

const SectionCard = styled(Card)`
  border-radius: 12px;
  padding: 1.5rem;
`

const RecentItem = styled.div<{$color: string}>`
  padding: 0.6rem 0.75rem;
  border-left: 3px solid ${(p) => p.$color};
  border-radius: 0 6px 6px 0;
  cursor: pointer;
  transition: background 0.15s ease;
  &:hover {
    background: rgba(255, 255, 255, 0.04);
  }
`

const RecentTitle = styled.div`
  font-size: 13px;
  font-weight: 500;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`

const RecentMeta = styled.div`
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: 6px;
`

const ActionBtn = styled.button<{$bg: string}>`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  padding: 0.75rem 1rem;
  background: ${(p) => p.$bg};
  border: none;
  border-radius: 8px;
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: opacity 0.15s, transform 0.15s;
  &:hover {
    opacity: 0.88;
    transform: translateX(3px);
  }
  svg {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
  }
`

const DeployRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
`

const DeployLabel = styled.div`
  font-size: 13px;
  font-weight: 500;
  color: #e2e8f0;
`

const DeploySub = styled.div`
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
`

const StatusIcon = styled.span<{$color: string}>`
  color: ${(p) => p.$color};
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 500;
`

const SectionHeading = styled.div`
  font-size: 15px;
  font-weight: 600;
  color: #e2e8f0;
  display: flex;
  align-items: center;
  gap: 8px;
`

const ItemCount = styled.span`
  font-size: 12px;
  color: #64748b;
  font-weight: 400;
  margin-left: auto;
`

/* ────────────────────────────────────────────
   Helpers
   ──────────────────────────────────────────── */

function getGreeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function getDocTitle(doc: RecentDoc): string {
  switch (doc._type) {
    case 'systemNote':
      return doc.title || 'Untitled Note'
    case 'backupLog':
      return `Backup \u2014 ${doc.status || 'Unknown'}`
    case 'systemProfile':
      return doc.hostname || 'Unnamed Profile'
    case 'siteContent':
      return doc.siteTitle || 'Site Content'
    default:
      return 'Untitled'
  }
}

function getDocSubtitle(doc: RecentDoc): string {
  switch (doc._type) {
    case 'systemNote':
      return doc.category || 'general'
    case 'backupLog':
      return doc.ranAt ? new Date(doc.ranAt).toLocaleDateString() : ''
    case 'systemProfile':
      return doc.device || ''
    case 'siteContent':
      return 'Singleton'
    default:
      return ''
  }
}

/* ────────────────────────────────────────────
   Component
   ──────────────────────────────────────────── */

export function DashboardTool() {
  const client = useClient({apiVersion: '2024-01-01'})
  const user = useCurrentUser()
  const router = useRouter()

  const [stats, setStats] = useState<Stats | null>(null)
  const [latestBackup, setLatestBackup] = useState<LatestBackup | null>(null)
  const [recentDocs, setRecentDocs] = useState<RecentDoc[]>([])
  const [loading, setLoading] = useState(true)
  const [deployState, setDeployState] = useState<Record<string, string>>({})

  /* Fetch data */
  useEffect(() => {
    Promise.all([client.fetch(STATS_QUERY), client.fetch(RECENT_QUERY)])
      .then(([s, r]) => {
        setStats({
          systemNotes: s.systemNotes,
          backupLogs: s.backupLogs,
          systemProfiles: s.systemProfiles,
        })
        setLatestBackup(s.latestBackup)
        setRecentDocs(r)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [client])

  /* Navigation */
  const editDoc = useCallback(
    (id: string, type: string) => {
      router.navigateIntent('edit', {id, type})
    },
    [router],
  )

  const createDoc = useCallback(
    (type: string) => {
      router.navigateIntent('create', {type})
    },
    [router],
  )

  /* Deploy */
  const handleDeploy = useCallback(
    async (env: string) => {
      const hookVar =
        env === 'production'
          ? process.env.SANITY_STUDIO_DEPLOY_HOOK
          : process.env.SANITY_STUDIO_DEPLOY_HOOK_STAGING

      if (!hookVar) {
        window.open('https://vercel.com/dashboard', '_blank')
        return
      }

      setDeployState((prev) => ({...prev, [env]: 'deploying'}))
      try {
        await fetch(hookVar, {method: 'POST'})
        setDeployState((prev) => ({...prev, [env]: 'triggered'}))
      } catch {
        setDeployState((prev) => ({...prev, [env]: 'error'}))
      }
      setTimeout(() => setDeployState((prev) => ({...prev, [env]: ''})), 4000)
    },
    [],
  )

  /* Loading state */
  if (loading) {
    return (
      <Flex align="center" justify="center" padding={6} style={{minHeight: '60vh'}}>
        <Spinner muted />
      </Flex>
    )
  }

  const displayName = user?.name?.split(' ')[0] || 'there'

  return (
    <Wrapper>
      <Stack space={5}>
        {/* ── Welcome + Stats ───────────────────── */}
        <WelcomeCard>
          <Flex gap={4} wrap="wrap" align="stretch">
            <div style={{flex: 3, minWidth: 300}}>
              <Stack space={4}>
                <div>
                  <h1
                    style={{
                      fontSize: 28,
                      fontWeight: 700,
                      color: '#e0e7ff',
                      margin: 0,
                    }}
                  >
                    <span role="img" aria-label="bolt">
                      &#9889;
                    </span>{' '}
                    {getGreeting()}, {displayName}
                  </h1>
                  <p style={{fontSize: 14, color: '#94a3b8', margin: '0.5rem 0 0'}}>
                    Your backup command center. Keep your uConsole configs sharp.
                  </p>
                </div>

                <Flex gap={3} wrap="wrap">
                  <StatCard $accent="#4ecdc4">
                    <StatLabel>System Notes</StatLabel>
                    <StatValue>{stats?.systemNotes ?? 0}</StatValue>
                  </StatCard>
                  <StatCard $accent="#ff6b6b">
                    <StatLabel>Backup Logs</StatLabel>
                    <StatValue>{stats?.backupLogs ?? 0}</StatValue>
                  </StatCard>
                  <StatCard $accent="#a78bfa">
                    <StatLabel>Profiles</StatLabel>
                    <StatValue>{stats?.systemProfiles ?? 0}</StatValue>
                  </StatCard>
                  <StatCard $accent="#fbbf24">
                    <StatLabel>Site Content</StatLabel>
                    <StatValue>1</StatValue>
                    <StatSub>Singleton</StatSub>
                  </StatCard>
                </Flex>
              </Stack>
            </div>

            <StatusCallout $status={latestBackup?.status}>
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: '0.06em',
                  color: '#e0e7ff',
                  marginBottom: 12,
                  textTransform: 'uppercase',
                }}
              >
                <span role="img" aria-label="sparkle">
                  &#10024;
                </span>{' '}
                Latest Backup
              </div>
              {latestBackup ? (
                <>
                  <div style={{fontSize: 18, fontWeight: 600, color: '#f1f5f9'}}>
                    {latestBackup.status === 'success' && (
                      <StatusIcon $color="#34d399">
                        <CheckmarkCircleIcon /> All systems green
                      </StatusIcon>
                    )}
                    {latestBackup.status === 'partial' && (
                      <StatusIcon $color="#fbbf24">Partial backup</StatusIcon>
                    )}
                    {latestBackup.status === 'failed' && (
                      <StatusIcon $color="#f87171">
                        <CloseCircleIcon /> Backup failed
                      </StatusIcon>
                    )}
                  </div>
                  <div style={{fontSize: 12, color: '#94a3b8', marginTop: 8}}>
                    {new Date(latestBackup.ranAt).toLocaleDateString()} &mdash;{' '}
                    {latestBackup.modules?.length || 0} modules ran
                  </div>
                </>
              ) : (
                <div style={{fontSize: 16, fontWeight: 500, color: '#94a3b8'}}>
                  No backups logged yet.
                  <br />
                  <span style={{fontSize: 13}}>
                    Add a backup log to track your system.
                  </span>
                </div>
              )}
            </StatusCallout>
          </Flex>
        </WelcomeCard>

        {/* ── Three-Column Layout ───────────────── */}
        <Grid columns={[1, 1, 3]} gap={4}>
          {/* Recently Edited */}
          <SectionCard tone="default" shadow={1}>
            <Stack space={4}>
              <SectionHeading>
                <span role="img" aria-label="folder">
                  &#128193;
                </span>{' '}
                Recently Edited
                <ItemCount>{recentDocs.length} items</ItemCount>
              </SectionHeading>
              <Stack space={2}>
                {recentDocs.map((doc) => {
                  const meta = TYPE_META[doc._type]
                  return (
                    <RecentItem
                      key={doc._id}
                      $color={meta?.color || '#64748b'}
                      onClick={() => editDoc(doc._id, doc._type)}
                    >
                      <RecentTitle>{getDocTitle(doc)}</RecentTitle>
                      <RecentMeta>
                        {meta?.label}
                        {getDocSubtitle(doc) && (
                          <>
                            <span>&middot;</span>
                            {getDocSubtitle(doc)}
                          </>
                        )}
                        <span>&middot;</span>
                        {timeAgo(doc._updatedAt)}
                      </RecentMeta>
                    </RecentItem>
                  )
                })}
                {recentDocs.length === 0 && (
                  <Text size={1} muted>
                    No documents yet. Create one to get started.
                  </Text>
                )}
              </Stack>
            </Stack>
          </SectionCard>

          {/* Quick Actions */}
          <SectionCard tone="default" shadow={1}>
            <Stack space={4}>
              <SectionHeading>
                <span role="img" aria-label="bolt">
                  &#9889;
                </span>{' '}
                Quick Actions
              </SectionHeading>
              <Stack space={2}>
                <ActionBtn
                  $bg="linear-gradient(135deg, #b45309, #d97706)"
                  onClick={() => editDoc('siteContent', 'siteContent')}
                >
                  <CogIcon /> Edit Site Content
                </ActionBtn>
                <ActionBtn
                  $bg="linear-gradient(135deg, #0d9488, #14b8a6)"
                  onClick={() => createDoc('systemNote')}
                >
                  <AddIcon /> New System Note
                </ActionBtn>
                <ActionBtn
                  $bg="linear-gradient(135deg, #dc2626, #ef4444)"
                  onClick={() => createDoc('backupLog')}
                >
                  <AddIcon /> New Backup Log
                </ActionBtn>
                <ActionBtn
                  $bg="linear-gradient(135deg, #7c3aed, #8b5cf6)"
                  onClick={() => createDoc('systemProfile')}
                >
                  <AddIcon /> New System Profile
                </ActionBtn>
                <ActionBtn
                  $bg="linear-gradient(135deg, #2563eb, #3b82f6)"
                  onClick={() =>
                    window.open('https://uconsole.cloud', '_blank')
                  }
                >
                  <DocumentIcon /> View Live Site
                </ActionBtn>
                <ActionBtn
                  $bg="linear-gradient(135deg, #475569, #64748b)"
                  onClick={() =>
                    window.open(
                      'https://github.com/mikevitelli/uconsole-dashboard',
                      '_blank',
                    )
                  }
                >
                  <EditIcon /> Open GitHub Repo
                </ActionBtn>
              </Stack>
            </Stack>
          </SectionCard>

          {/* Deploy Website */}
          <SectionCard tone="default" shadow={1}>
            <Stack space={4}>
              <SectionHeading>
                <span role="img" aria-label="rocket">
                  &#128640;
                </span>{' '}
                Deploy Website
              </SectionHeading>
              <Text size={1} muted>
                Trigger a deploy on Vercel
              </Text>

              <Stack space={3}>
                <DeployRow>
                  <div>
                    <DeployLabel>Production</DeployLabel>
                    <DeploySub>uconsole.cloud</DeploySub>
                    {deployState.production === 'triggered' && (
                      <StatusIcon $color="#34d399">
                        <CheckmarkCircleIcon /> Deploy triggered
                      </StatusIcon>
                    )}
                    {deployState.production === 'error' && (
                      <StatusIcon $color="#f87171">
                        <CloseCircleIcon /> Failed
                      </StatusIcon>
                    )}
                  </div>
                  <Button
                    text={
                      deployState.production === 'deploying'
                        ? 'Deploying\u2026'
                        : 'Deploy'
                    }
                    tone="primary"
                    mode="ghost"
                    onClick={() => handleDeploy('production')}
                    disabled={!!deployState.production}
                  />
                </DeployRow>

                <DeployRow>
                  <div>
                    <DeployLabel>Preview / QA</DeployLabel>
                    <DeploySub>*.vercel.app</DeploySub>
                    {deployState.preview === 'triggered' && (
                      <StatusIcon $color="#34d399">
                        <CheckmarkCircleIcon /> Deploy triggered
                      </StatusIcon>
                    )}
                    {deployState.preview === 'error' && (
                      <StatusIcon $color="#f87171">
                        <CloseCircleIcon /> Failed
                      </StatusIcon>
                    )}
                  </div>
                  <Button
                    text={
                      deployState.preview === 'deploying'
                        ? 'Deploying\u2026'
                        : 'Deploy'
                    }
                    tone="caution"
                    mode="ghost"
                    onClick={() => handleDeploy('preview')}
                    disabled={!!deployState.preview}
                  />
                </DeployRow>
              </Stack>

              <div style={{marginTop: 'auto', paddingTop: 8}}>
                <Button
                  text="Manage on Vercel"
                  mode="ghost"
                  tone="default"
                  style={{width: '100%'}}
                  onClick={() => window.open('https://vercel.com/dashboard', '_blank')}
                />
              </div>
            </Stack>
          </SectionCard>
        </Grid>
      </Stack>
    </Wrapper>
  )
}
