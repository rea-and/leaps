package net.carlevato.leapsquick;

import android.app.*; import android.appwidget.*; import android.content.*; import android.os.*; import android.widget.*; import java.io.*; import java.net.*; import java.nio.charset.StandardCharsets; import java.util.concurrent.*;

public class LeapsWidget extends AppWidgetProvider {
  static final String ACTION="net.carlevato.leapsquick.RECORD";
  public void onUpdate(Context c, AppWidgetManager m, int[] ids){ for(int id:ids) render(c,m,id,"Tap to record"); }
  public void onReceive(Context c, Intent i){ super.onReceive(c,i); if(!ACTION.equals(i.getAction())) return; PendingResult pending=goAsync(); String kind=i.getStringExtra("kind"); Executors.newSingleThreadExecutor().execute(()->{ String message=record(c,kind); AppWidgetManager m=AppWidgetManager.getInstance(c); for(int id:m.getAppWidgetIds(new ComponentName(c,LeapsWidget.class))) render(c,m,id,message); pending.finish(); }); }
  static void render(Context c, AppWidgetManager m, int id, String status){ RemoteViews v=new RemoteViews(c.getPackageName(),R.layout.leaps_widget); v.setOnClickPendingIntent(R.id.medium,pending(c,"medium",id)); v.setOnClickPendingIntent(R.id.pills,pending(c,"pills",id)); m.updateAppWidget(id,v); }
  static PendingIntent pending(Context c,String kind,int id){ Intent i=new Intent(c,LeapsWidget.class).setAction(ACTION).putExtra("kind",kind); return PendingIntent.getBroadcast(c,id+("pills".equals(kind)?10000:0),i,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE); }
  static String record(Context c,String kind){ try { String base=c.getSharedPreferences("leaps",0).getString("url","https://carlevato.net/leaps").replaceAll("/+$",""); HttpURLConnection h=(HttpURLConnection)new URL(base+"/api/quick-record").openConnection(); h.setRequestMethod("POST"); h.setRequestProperty("Content-Type","application/json"); h.setDoOutput(true); h.getOutputStream().write(("{\"kind\":\""+kind+"\"}").getBytes(StandardCharsets.UTF_8)); return h.getResponseCode()<300 ? ("medium".equals(kind)?"Medium recorded":"Pills recorded") : "Server error"; } catch(Exception e){ return "Could not connect"; } }
}
