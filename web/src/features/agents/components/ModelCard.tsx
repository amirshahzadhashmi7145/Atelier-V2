import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export type ModelCardModel = {
  name: string
  contextWindow: number
  speedTier: string
  fitLine: string | null
  priceInPerM: number | null
  priceOutPerM: number | null
  benchmarks: { name: string; score: number; sourceUrl: string }[]
}

export function ModelCard({ model }: { model: ModelCardModel }) {
  const sourced = model.benchmarks.filter((item) => item.sourceUrl)
  const showPrices = model.priceInPerM != null && model.priceOutPerM != null && sourced.length > 0
  const hasStats = Boolean(model.fitLine) || showPrices || sourced.length > 0
  return (
    <Card>
      <CardHeader>
        <CardTitle>{model.name}</CardTitle>
        <CardDescription>
          {model.contextWindow.toLocaleString()} token context · {model.speedTier}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {model.fitLine ? <p>{model.fitLine}</p> : null}
        {showPrices ? (
          <p>
            ${model.priceInPerM} in / ${model.priceOutPerM} out per million tokens
          </p>
        ) : null}
        {sourced.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {sourced.map((item) => (
              <Badge key={item.name} variant="outline" render={<a href={item.sourceUrl} />}>
                {item.name}: {item.score}
              </Badge>
            ))}
          </div>
        ) : null}
        {hasStats ? null : <p>no stats entered</p>}
      </CardContent>
    </Card>
  )
}
