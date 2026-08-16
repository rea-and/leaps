package net.carlevato.leapsquick;

import android.Manifest; import android.app.*; import android.content.*; import android.content.pm.PackageManager; import android.net.Uri; import android.os.*; import android.provider.Settings; import android.widget.*;

public class MainActivity extends Activity {
  private static final int[] OPACITIES={255,210,160,105};
  public void onCreate(Bundle state) { super.onCreate(state); setContentView(R.layout.activity_main);
    EditText url=findViewById(R.id.url); Spinner transparency=findViewById(R.id.transparency); TextView status=findViewById(R.id.status);
    ArrayAdapter<String> options=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"Solid grey","Light grey","Soft grey","Transparent grey"});
    transparency.setAdapter(options);
    url.setText(getSharedPreferences("leaps",0).getString("url","https://carlevato.net/leaps"));
    int savedOpacity=getSharedPreferences("leaps",0).getInt("widgetOpacity",210);
    for(int index=0;index<OPACITIES.length;index++) if(OPACITIES[index]==savedOpacity) transparency.setSelection(index);
    findViewById(R.id.save).setOnClickListener(v->{ String value=url.getText().toString().replaceAll("/+$",""); int opacity=OPACITIES[transparency.getSelectedItemPosition()]; getSharedPreferences("leaps",0).edit().putString("url",value).putInt("widgetOpacity",opacity).apply(); LeapsWidget.refreshAll(this,null,null); PillReminderReceiver.scheduleAll(this); status.setText("Saved. Widget appearance and reminders updated."); });
    findViewById(R.id.enable_reminders).setOnClickListener(v->{ enableReminders(status); });
    PillReminderReceiver.scheduleAll(this);
  }
  public void onResume(){ super.onResume(); PillReminderReceiver.scheduleAll(this); }
  private void enableReminders(TextView status){
    if(Build.VERSION.SDK_INT>=33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED) requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},11);
    if(Build.VERSION.SDK_INT>=31 && !((AlarmManager)getSystemService(ALARM_SERVICE)).canScheduleExactAlarms()) startActivity(new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM, Uri.parse("package:"+getPackageName())));
    PillReminderReceiver.scheduleAll(this);
    status.setText("Pill reminders scheduled for 8:30am and 10:30pm.");
  }
}
