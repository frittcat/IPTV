package tv.familystream.client

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

internal data class Channel(
    val id: String,
    val name: String,
    val country: String?,
    val categories: String?,
    val logo: String?,
    val hasEpg: Boolean,
)

internal data class CatalogItem(
    val id: String,
    val title: String,
    val year: Int?,
    val plot: String?,
    val poster: String?,
    val backdrop: String?,
    val rating: Double?,
    val itemType: String,
    val playable: Boolean,
)

internal data class HomeFeed(
    val live: List<Channel>,
    val movies: List<CatalogItem>,
    val series: List<CatalogItem>,
)

internal data class Season(
    val number: Int,
    val title: String,
    val episodeCount: Int,
)

internal data class SeriesDetail(
    val id: String,
    val title: String,
    val year: Int?,
    val plot: String?,
    val poster: String?,
    val backdrop: String?,
    val seasons: List<Season>,
)

internal data class Episode(
    val id: String,
    val season: Int,
    val number: Int,
    val title: String,
    val plot: String?,
    val playable: Boolean,
)

internal data class PlaybackResolution(
    val url: String,
    val mimeType: String?,
    val protocol: String?,
    val videoCodec: String?,
    val audioCodec: String?,
    val width: Int?,
    val height: Int?,
)

internal class FamilyStreamApi(
    private val baseUrl: String,
    private val maxHeight: Int = 2160,
) {
    private val deviceHeaders = mapOf(
        "X-FamilyStream-Device" to "android-tv-modern",
        "X-FamilyStream-Video-Codecs" to "hevc,h265,h264,avc",
        "X-FamilyStream-Max-Height" to maxHeight.toString(),
        "Accept" to "application/json",
    )

    fun home(): HomeFeed {
        val root = getObject("/api/v1/home?limit=18")
        return HomeFeed(
            live = parseChannels(root.optJSONArray("live")),
            movies = parseCatalog(root.optJSONArray("movies"), "movie"),
            series = parseCatalog(root.optJSONArray("series"), "series"),
        )
    }

    fun channels(limit: Int = 300): List<Channel> {
        val root = getObject("/api/v1/live/channels?limit=${limit.coerceIn(1, 500)}")
        return parseChannels(root.optJSONArray("items"))
    }

    fun catalog(itemType: String, limit: Int = 120): List<CatalogItem> {
        require(itemType == "movie" || itemType == "series")
        val root = getObject("/api/v1/catalog/$itemType?limit=${limit.coerceIn(1, 200)}")
        return parseCatalog(root.optJSONArray("items"), itemType)
    }

    fun seriesDetail(id: String): SeriesDetail {
        val root = getObject("/api/v1/catalog/series/${pathPart(id)}")
        val seasonsArray = root.optJSONArray("seasons") ?: JSONArray()
        val seasons = buildList {
            for (index in 0 until seasonsArray.length()) {
                val item = seasonsArray.optJSONObject(index) ?: continue
                add(
                    Season(
                        number = item.optInt("season_number", 0),
                        title = item.optString("title", "Temporada ${item.optInt("season_number", 0)}"),
                        episodeCount = item.optInt("episode_count", 0),
                    ),
                )
            }
        }
        return SeriesDetail(
            id = root.optString("id"),
            title = root.optString("title"),
            year = root.optIntOrNull("year"),
            plot = root.optNullableString("plot"),
            poster = root.optNullableString("poster"),
            backdrop = root.optNullableString("backdrop"),
            seasons = seasons,
        )
    }

    fun episodes(seriesId: String, season: Int): List<Episode> {
        val root = getObject("/api/v1/series/${pathPart(seriesId)}/episodes?season=$season")
        val array = root.optJSONArray("items") ?: JSONArray()
        return buildList {
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                add(
                    Episode(
                        id = item.optString("id"),
                        season = item.optInt("season_number", season),
                        number = item.optInt("episode_number", 0),
                        title = item.optString("title", "Episódio ${item.optInt("episode_number", 0)}"),
                        plot = item.optNullableString("plot"),
                        playable = item.optBoolean("playable", false),
                    ),
                )
            }
        }
    }

    fun resolvePlayback(kind: String, id: String): PlaybackResolution {
        val root = getObject("/api/v1/playback/resolve/$kind/${pathPart(id)}")
        return PlaybackResolution(
            url = root.getString("playback_url"),
            mimeType = root.optNullableString("mime_type"),
            protocol = root.optNullableString("protocol"),
            videoCodec = root.optNullableString("video_codec"),
            audioCodec = root.optNullableString("audio_codec"),
            width = root.optIntOrNull("width"),
            height = root.optIntOrNull("height"),
        )
    }

    fun requestHeaders(): Map<String, String> = deviceHeaders

    private fun parseChannels(array: JSONArray?): List<Channel> {
        if (array == null) return emptyList()
        return buildList {
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                val id = item.optString("id")
                if (id.isBlank()) continue
                add(
                    Channel(
                        id = id,
                        name = item.optString("name", id),
                        country = item.optNullableString("country"),
                        categories = item.optNullableString("categories"),
                        logo = item.optNullableString("logo"),
                        hasEpg = item.optBoolean("has_epg", false),
                    ),
                )
            }
        }
    }

    private fun parseCatalog(array: JSONArray?, itemType: String): List<CatalogItem> {
        if (array == null) return emptyList()
        return buildList {
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                val id = item.optString("id")
                if (id.isBlank()) continue
                add(
                    CatalogItem(
                        id = id,
                        title = item.optString("title", id),
                        year = item.optIntOrNull("year"),
                        plot = item.optNullableString("plot"),
                        poster = item.optNullableString("poster"),
                        backdrop = item.optNullableString("backdrop"),
                        rating = item.optDoubleOrNull("rating"),
                        itemType = item.optString("item_type", itemType),
                        playable = item.optBoolean("playable", false),
                    ),
                )
            }
        }
    }

    private fun getObject(path: String): JSONObject {
        val connection = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            connectTimeout = 8_000
            readTimeout = 12_000
            requestMethod = "GET"
            deviceHeaders.forEach { (key, value) -> setRequestProperty(key, value) }
        }
        return try {
            val code = connection.responseCode
            if (code !in 200..299) {
                throw IllegalStateException("FamilyStream HTTP $code")
            }
            val payload = connection.inputStream.bufferedReader().use { it.readText() }
            JSONObject(payload)
        } finally {
            connection.disconnect()
        }
    }

    private fun pathPart(value: String): String = java.net.URLEncoder.encode(value, Charsets.UTF_8.name())
}

private fun JSONObject.optNullableString(name: String): String? {
    if (!has(name) || isNull(name)) return null
    return optString(name).takeIf { it.isNotBlank() && !it.equals("null", ignoreCase = true) }
}

private fun JSONObject.optIntOrNull(name: String): Int? {
    if (!has(name) || isNull(name)) return null
    return runCatching { getInt(name) }.getOrNull()
}

private fun JSONObject.optDoubleOrNull(name: String): Double? {
    if (!has(name) || isNull(name)) return null
    return runCatching { getDouble(name) }.getOrNull()
}
